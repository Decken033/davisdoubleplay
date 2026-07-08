# 因子计算和选股逻辑
import pandas as pd
import numpy as np
from data_loader import DataLoader


class StockSelector:
    """基于财务数据的选股器"""

    def __init__(self, data_loader):
        """
        初始化选股器

        Args:
            data_loader: DataLoader实例
        """
        self.loader = data_loader
        self.quarterly_net_profit = None  # 单季度净利润
        self.quarterly_oper_rev = None  # 单季度营收
        self.yoy_growth = None  # 同比增速（预计算）
        self.second_order = None  # 二阶增速（预计算）

    def calculate_quarterly_data(self):
        """
        加载单季度数据（数据源已经是单季度，无需还原）
        并预计算同比增速和二阶增速
        """
        print("\n正在加载单季度数据...")

        # 数据源已经是单季度数据，直接使用
        self.quarterly_net_profit = self.loader.net_profit.copy()
        self.quarterly_oper_rev = self.loader.oper_rev.copy()

        # 确保索引是字符串类型（YYYYMMDD格式）
        self.quarterly_net_profit.index = self.quarterly_net_profit.index.astype(str)
        self.quarterly_oper_rev.index = self.quarterly_oper_rev.index.astype(str)

        print(f"单季度净利润: {self.quarterly_net_profit.shape}")
        print(f"单季度营收: {self.quarterly_oper_rev.shape}")

        # 预计算同比增速和二阶增速（避免在每次调仓时重复计算）
        print("\n正在预计算同比增速和二阶增速...")
        self.yoy_growth = self.calculate_yoy_growth()
        self.second_order = self.calculate_second_order_growth(self.yoy_growth)
        print(f"同比增速: {self.yoy_growth.shape}")
        print(f"二阶增速: {self.second_order.shape}")

    def calculate_yoy_growth(self):
        """
        计算单季度净利润同比增速

        Returns:
            DataFrame: 同比增速 (date × stock_id)
        """
        # 获取去年同期的单季度净利润
        dates = sorted(self.quarterly_net_profit.index)
        yoy_growth = pd.DataFrame(index=dates, columns=self.quarterly_net_profit.columns)

        for date in dates:
            # 确保日期是字符串类型
            date = str(date)

            # 计算去年同期日期
            year = int(date[:4])
            last_year_date = str(year - 1) + date[4:]

            if last_year_date in self.quarterly_net_profit.index:
                current = self.quarterly_net_profit.loc[date]
                last_year = self.quarterly_net_profit.loc[last_year_date]

                # 同比增速 = (本期 - 去年同期) / abs(去年同期)
                # 注意：去年同期可能为负，用绝对值作为基数
                # 关键：去年同期为0时，将inf替换为NaN
                with np.errstate(divide='ignore', invalid='ignore'):
                    growth = (current - last_year) / last_year.abs()
                    # 将inf和-inf替换为NaN（去年同期为0的情况）
                    growth = growth.replace([np.inf, -np.inf], np.nan)
                yoy_growth.loc[date] = growth

        return yoy_growth

    def calculate_second_order_growth(self, yoy_growth):
        """
        计算二阶增速（增速的增速）

        Args:
            yoy_growth: 同比增速 DataFrame

        Returns:
            DataFrame: 二阶增速 (date × stock_id)
        """
        dates = sorted(yoy_growth.index)
        second_order = pd.DataFrame(index=dates, columns=yoy_growth.columns)

        for i, date in enumerate(dates):
            if i == 0:
                continue

            # 获取上一期（上个季度）
            prev_date = dates[i - 1]
            current_growth = yoy_growth.loc[date]
            prev_growth = yoy_growth.loc[prev_date]

            # 二阶增速 = 本期增速 - 上期增速
            second_order.loc[date] = current_growth - prev_growth

        return second_order

    def get_top_stocks(self, rebalance_date, top_n=25):
        """
        根据筛选规则选择股票

        筛选规则：
        1. 当期单季度净利润同比增速为正
        2. 前期净利润大于 300 万
        3. 上一期单季度净利润同比增速为正
        4. 当期单季度净利润同比增速相较上一期继续提升（二阶增速为正）
        5. 上一期单季度营收为正

        排序规则：
        按二阶增速降序排列，选择前 top_n 个样本

        Args:
            rebalance_date: 调仓日期
            top_n: 选择股票数量，默认25

        Returns:
            list: 选中的股票代码列表
        """
        # 使用预计算的同比增速和二阶增速（避免重复计算）
        if self.yoy_growth is None or self.second_order is None:
            raise ValueError("请先调用calculate_quarterly_data()进行数据初始化")

        yoy_growth = self.yoy_growth
        second_order = self.second_order

        # 获取所有报告期日期（按时间排序）
        report_dates = sorted(self.quarterly_net_profit.index)

        print(f"\n调仓日: {rebalance_date}")

        # 获取所有潜在股票（只做基础过滤：退市和无基础信息）
        if self.loader.use_stock_filter and self.loader.stock_filter:
            all_stocks = list(self.quarterly_net_profit.columns)
            potential_stocks = []
            for stock in all_stocks:
                list_date = self.loader.stock_filter.get_list_date(stock)
                if list_date is None:
                    continue
                # 注意：退市判断仍使用调仓日，因为我们要确保调仓时股票未退市
                # ST和新股判断会在循环内使用披露日判断
                if self.loader.stock_filter.is_delisted(stock, rebalance_date):
                    continue
                potential_stocks.append(stock)
        else:
            potential_stocks = list(self.quarterly_net_profit.columns)

        # 应用筛选规则
        candidates = []
        filter_stats = {
            'insufficient_reports': 0,
            'non_standard_quarter': 0,
            'st_filtered': 0,
            'new_stock_filtered': 0,
            'data_missing': 0,
            'current_yoy_negative': 0,
            'prev_profit_low': 0,
            'prev_yoy_negative': 0,
            'second_order_negative': 0,
            'prev_rev_negative': 0,
            'passed': 0
        }

        # 预先计算财务数据可用的报告期集合（避免在循环内重复计算）
        available_financial_dates = set(report_dates)

        for stock in potential_stocks:
            # 为该股票单独确定在调仓日已披露的所有报告期
            stock_reports = self.loader.report_dates[
                self.loader.report_dates['stock_id'] == stock
            ].copy()

            # 筛选出在调仓日前已披露的报告期
            stock_reports = stock_reports[
                (stock_reports['issuing_date'].notna()) &
                (stock_reports['issuing_date'] <= rebalance_date)
            ].sort_values('date')

            # 关键：必须同时存在于财务数据表中（两个数据源的交集）
            stock_reports = stock_reports[stock_reports['date'].isin(available_financial_dates)]

            # 该股票至少需要2个已披露且有财务数据的报告期才能计算二阶增速
            if len(stock_reports) < 2:
                filter_stats['insufficient_reports'] += 1
                continue

            # 获取该股票自己的当期和前期报告期
            stock_current_report = stock_reports.iloc[-1]['date']
            stock_disclosure_date = stock_reports.iloc[-1]['issuing_date']

            # 计算理论上的前期报告期（当期往前推一个季度）
            # 报告期格式: YYYYMMDD，其中月日部分为 0331/0630/0930/1231
            current_year = int(stock_current_report[:4])
            current_month_day = stock_current_report[4:]

            # 根据当期的月日判断季度，并计算前一季度
            if current_month_day == '0331':  # Q1
                expected_prev_report = f"{current_year - 1}1231"  # 上年Q4
            elif current_month_day == '0630':  # Q2
                expected_prev_report = f"{current_year}0331"  # 本年Q1
            elif current_month_day == '0930':  # Q3
                expected_prev_report = f"{current_year}0630"  # 本年Q2
            elif current_month_day == '1231':  # Q4
                expected_prev_report = f"{current_year}0930"  # 本年Q3
            else:
                # 非标准季度报告期，跳过
                filter_stats['non_standard_quarter'] += 1
                continue

            # 验证理论上的前期报告期是否在已披露列表中
            # 必须确保前后两期是连续的季度，才能计算有意义的二阶增速
            if expected_prev_report not in stock_reports['date'].values:
                filter_stats['insufficient_reports'] += 1
                continue

            stock_prev_report = expected_prev_report

            # 在该股票的当期报告披露日判断其是否有效
            if self.loader.use_stock_filter and self.loader.stock_filter:
                # 判断是否ST
                if self.loader.stock_filter.is_st_stock(stock, stock_disclosure_date):
                    filter_stats['st_filtered'] += 1
                    continue

                # 判断是否新股（上市不足252个交易日）
                if self.loader.stock_filter.is_new_stock(stock, stock_disclosure_date, min_list_days=252):
                    filter_stats['new_stock_filtered'] += 1
                    continue

            # 获取财务数据（使用该股票自己的报告期）
            # 增加安全检查：确保索引和列都存在
            try:
                current_profit = self.quarterly_net_profit.loc[stock_current_report, stock]
                prev_profit = self.quarterly_net_profit.loc[stock_prev_report, stock]
                prev_rev = self.quarterly_oper_rev.loc[stock_prev_report, stock]

                current_yoy = yoy_growth.loc[stock_current_report, stock]
                prev_yoy = yoy_growth.loc[stock_prev_report, stock]
                second_order_val = second_order.loc[stock_current_report, stock]
            except (KeyError, IndexError):
                # 即使通过了交集过滤，某些边缘情况下仍可能访问失败
                filter_stats['data_missing'] += 1
                continue

            # 跳过数据缺失的股票（NaN值）
            if pd.isna(current_profit) or pd.isna(prev_profit) or pd.isna(prev_rev) or \
               pd.isna(current_yoy) or pd.isna(prev_yoy) or pd.isna(second_order_val):
                filter_stats['data_missing'] += 1
                continue

            # 规则1: 当期单季度净利润同比增速为正
            if current_yoy <= 0:
                filter_stats['current_yoy_negative'] += 1
                continue

            # 规则2: 前期净利润大于 300 万
            if prev_profit <= 3000000:
                filter_stats['prev_profit_low'] += 1
                continue

            # 规则3: 上一期单季度净利润同比增速为正
            if prev_yoy <= 0:
                filter_stats['prev_yoy_negative'] += 1
                continue

            # 规则4: 二阶增速为正
            if second_order_val <= 0:
                filter_stats['second_order_negative'] += 1
                continue

            # 规则5: 上一期单季度营收为正
            if prev_rev <= 0:
                filter_stats['prev_rev_negative'] += 1
                continue

            # 通过所有筛选
            filter_stats['passed'] += 1
            candidates.append({
                'stock_id': stock,
                'second_order_growth': second_order_val,
                'current_yoy': current_yoy,
                'prev_yoy': prev_yoy,
                'current_profit': current_profit,
                'prev_profit': prev_profit,
                'prev_rev': prev_rev,
                'current_report': stock_current_report,
                'prev_report': stock_prev_report
            })

        # 打印筛选统计
        print(f"  筛选统计:")
        print(f"    潜在股票数: {len(potential_stocks)}")
        print(f"    报告期不足2个: {filter_stats['insufficient_reports']}")
        print(f"    非标准季度: {filter_stats['non_standard_quarter']}")
        if self.loader.use_stock_filter and self.loader.stock_filter:
            print(f"    ST股票: {filter_stats['st_filtered']}")
            print(f"    新股: {filter_stats['new_stock_filtered']}")
        print(f"    数据缺失: {filter_stats['data_missing']}")
        print(f"    当期同比增速<=0: {filter_stats['current_yoy_negative']}")
        print(f"    前期利润<=300万: {filter_stats['prev_profit_low']}")
        print(f"    前期同比增速<=0: {filter_stats['prev_yoy_negative']}")
        print(f"    二阶增速<=0: {filter_stats['second_order_negative']}")
        print(f"    前期营收<=0: {filter_stats['prev_rev_negative']}")
        print(f"    通过筛选: {filter_stats['passed']}")

        # 转换为DataFrame并排序
        if len(candidates) == 0:
            print(f"  筛选结果: 无符合条件的股票")
            return []

        candidates_df = pd.DataFrame(candidates)

        # 检查是否存在重复的股票（理论上不应该有，但做一次防御性检查）
        if candidates_df['stock_id'].duplicated().any():
            print(f"  警告：发现重复股票，去重前 {len(candidates_df)} 只")
            candidates_df = candidates_df.drop_duplicates(subset='stock_id', keep='first')
            print(f"  去重后 {len(candidates_df)} 只")

        candidates_df = candidates_df.sort_values('second_order_growth', ascending=False)

        # 选择前 top_n 只
        top_stocks = candidates_df.head(top_n)

        print(f"  最终选择前 {min(top_n, len(top_stocks))} 只股票")

        return list(top_stocks['stock_id'])


if __name__ == '__main__':
    # 测试代码
    print("=== 股票选择器测试 ===\n")

    # 初始化数据加载器
    loader = DataLoader(
        adj_close_path='adj_close.csv',
        pe_ttm_path='pe_ttm_data.csv',
        net_profit_path='AShareIncome_Q.csv',
        oper_rev_path='AShareIncome_Q.csv',
        report_date_path='AShareIssuingDatePredict.csv',
        actual_disclosure_date_path='AShareIssuingDatePredict.csv',
        use_stock_filter=True,
        description_path='AShareDescription.xlsx',
        st_path='AShareST.xlsx'
    )
    loader.load_data()

    # 初始化选股器
    selector = StockSelector(loader)
    selector.calculate_quarterly_data()

    # 获取调仓日期
    rebalance_dates = loader.get_rebalance_dates()
    print(f"\n调仓日期数量: {len(rebalance_dates)}")

    # 测试第一个调仓日
    if len(rebalance_dates) > 0:
        test_date = rebalance_dates[0]
        print(f"\n测试调仓日: {test_date}")
        top_stocks = selector.get_top_stocks(test_date, top_n=25)

        if len(top_stocks) > 0:
            print(f"\n选中的股票 ({len(top_stocks)} 只):")
            for i, stock in enumerate(top_stocks, 1):
                print(f"  {i}. {stock}")
        else:
            print("\n未选出股票")