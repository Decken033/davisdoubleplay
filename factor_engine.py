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

    def calculate_quarterly_data(self):
        """
        加载单季度数据（数据源已经是单季度，无需还原）
        """
        print("\n正在加载单季度数据...")

        # 数据源已经是单季度数据，直接使用
        self.quarterly_net_profit = self.loader.net_profit.copy()
        self.quarterly_oper_rev = self.loader.oper_rev.copy()

        print(f"单季度净利润: {self.quarterly_net_profit.shape}")
        print(f"单季度营收: {self.quarterly_oper_rev.shape}")

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
            # 计算去年同期日期
            year = int(date[:4])
            last_year_date = str(year - 1) + date[4:]

            if last_year_date in self.quarterly_net_profit.index:
                current = self.quarterly_net_profit.loc[date]
                last_year = self.quarterly_net_profit.loc[last_year_date]

                # 同比增速 = (本期 - 去年同期) / abs(去年同期)
                # 注意：去年同期可能为负，用绝对值作为基数
                yoy_growth.loc[date] = (current - last_year) / last_year.abs()

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
        # 计算同比增速和二阶增速
        yoy_growth = self.calculate_yoy_growth()
        second_order = self.calculate_second_order_growth(yoy_growth)

        # 获取所有报告期日期（按时间排序）
        report_dates = sorted(self.quarterly_net_profit.index)

        # 找到在调仓日前已披露的最新报告期
        available_reports = [d for d in report_dates
                           if self._is_report_disclosed(d, rebalance_date)]

        if len(available_reports) < 2:
            print(f"警告: {rebalance_date} 前可用报告期不足2个，无法选股")
            return []

        current_report = available_reports[-1]  # 当期
        prev_report = available_reports[-2]  # 前期

        print(f"\n调仓日: {rebalance_date}")
        print(f"  当期报告期: {current_report}")
        print(f"  前期报告期: {prev_report}")

        # 获取股票池（使用股票过滤器剔除ST和不符合条件的股票）
        if self.loader.use_stock_filter and self.loader.stock_filter:
            valid_stocks = self.loader.stock_filter.get_valid_stocks(rebalance_date)
        else:
            valid_stocks = list(self.quarterly_net_profit.columns)

        # 应用筛选规则
        candidates = []

        for stock in valid_stocks:
            # 获取数据
            current_profit = self.quarterly_net_profit.loc[current_report, stock]
            prev_profit = self.quarterly_net_profit.loc[prev_report, stock]
            prev_rev = self.quarterly_oper_rev.loc[prev_report, stock]

            current_yoy = yoy_growth.loc[current_report, stock]
            prev_yoy = yoy_growth.loc[prev_report, stock]
            second_order_val = second_order.loc[current_report, stock]

            # 跳过数据缺失的股票
            if pd.isna(current_profit) or pd.isna(prev_profit) or pd.isna(prev_rev) or \
               pd.isna(current_yoy) or pd.isna(prev_yoy) or pd.isna(second_order_val):
                continue

            # 规则1: 当期单季度净利润同比增速为正
            if current_yoy <= 0:
                continue

            # 规则2: 前期净利润大于 300 万
            if prev_profit <= 3000000:
                continue

            # 规则3: 上一期单季度净利润同比增速为正
            if prev_yoy <= 0:
                continue

            # 规则4: 二阶增速为正
            if second_order_val <= 0:
                continue

            # 规则5: 上一期单季度营收为正
            if prev_rev <= 0:
                continue

            # 通过所有筛选
            candidates.append({
                'stock_id': stock,
                'second_order_growth': second_order_val,
                'current_yoy': current_yoy,
                'prev_yoy': prev_yoy,
                'current_profit': current_profit,
                'prev_profit': prev_profit,
                'prev_rev': prev_rev
            })

        # 转换为DataFrame并排序
        if len(candidates) == 0:
            print(f"  筛选结果: 无符合条件的股票")
            return []

        candidates_df = pd.DataFrame(candidates)
        candidates_df = candidates_df.sort_values('second_order_growth', ascending=False)

        # 选择前 top_n 只
        top_stocks = candidates_df.head(top_n)

        print(f"  筛选结果: {len(candidates_df)} 只股票符合条件")
        print(f"  选择前 {min(top_n, len(top_stocks))} 只股票")

        return list(top_stocks['stock_id'])

    def _is_report_disclosed(self, report_date, as_of_date):
        """
        判断某个报告期在指定日期前是否已披露

        Args:
            report_date: 报告期（格式：'YYYYMMDD'）
            as_of_date: 查询日期（格式：'YYYYMMDD'）

        Returns:
            bool: 是否已披露
        """
        # 在report_dates中查找该报告期的披露日期
        report_info = self.loader.report_dates[
            self.loader.report_dates['date'] == report_date
        ]

        if len(report_info) == 0:
            return False

        # 检查是否有任何股票在as_of_date前披露了该报告期
        # 这里简化处理：只要有股票披露了，就认为该报告期可用
        disclosed = report_info[report_info['issuing_date'] <= as_of_date]
        return len(disclosed) > 0


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