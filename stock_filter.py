import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class StockFilter:
    """股票池过滤器 - 用于剔除ST股票、新股等"""

    def __init__(self, description_path='AShareDescription.xlsx', st_path='AShareST.xlsx'):
        """
        初始化股票过滤器

        Args:
            description_path: 上市日期数据路径
            st_path: ST状态数据路径
        """
        self.description_path = description_path
        self.st_path = st_path
        self.description_df = None
        self.st_df = None

    def load_data(self):
        """加载过滤所需的数据"""
        print(f"正在加载股票过滤数据:")
        print(f"  上市日期: {self.description_path}")
        print(f"  ST状态: {self.st_path}")

        # 加载上市和退市日期数据
        self.description_df = pd.read_excel(self.description_path)
        # 确保日期列为字符串格式
        self.description_df['S_INFO_LISTDATE'] = self.description_df['S_INFO_LISTDATE'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        self.description_df['S_INFO_DELISTDATE']=self.description_df['S_INFO_DELISTDATE'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        # 加载ST数据
        self.st_df = pd.read_excel(self.st_path)
        # 确保日期列为字符串格式
        self.st_df['ENTRY_DT'] = self.st_df['ENTRY_DT'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        self.st_df['REMOVE_DT'] = self.st_df['REMOVE_DT'].astype(str).str.replace(r'\.0$', '', regex=True).str.replace('nan', '').str.strip()

        print(f"数据加载完成:")
        print(f"  股票总数: {len(self.description_df)}")
        print(f"  ST记录数: {len(self.st_df)}")

    def is_st_stock(self, stock_code, check_date):
        """
        判断股票在指定日期是否为ST状态

        Args:
            stock_code: 股票代码
            check_date: 查询日期（格式：'YYYYMMDD'）

        Returns:
            bool: True表示是ST股票
        """
        if self.st_df is None:
            raise ValueError("请先调用load_data()加载数据")

        # 筛选该股票的ST记录
        stock_st = self.st_df[self.st_df['S_INFO_WINDCODE'] == stock_code]

        if len(stock_st) == 0:
            return False

        # 检查是否在ST期间内
        for _, row in stock_st.iterrows():
            entry_dt = row['ENTRY_DT']
            remove_dt = row['REMOVE_DT']

            # 如果进入日期无效，跳过
            if pd.isna(entry_dt) or entry_dt == '' or entry_dt == 'nan':
                continue

            # 如果在进入日期之后
            if check_date >= entry_dt:
                # 如果移除日期为空，说明当前仍是ST
                if pd.isna(remove_dt) or remove_dt == '' or remove_dt == 'nan':
                    return True
                # 如果在移除日期之前，说明在ST期间
                elif check_date < remove_dt:
                    return True

        return False

    def get_list_date(self, stock_code):
        """
        获取股票上市日期

        Args:
            stock_code: 股票代码

        Returns:
            str: 上市日期（格式：'YYYYMMDD'），如果找不到返回None
        """
        if self.description_df is None:
            raise ValueError("请先调用load_data()加载数据")

        stock_info = self.description_df[self.description_df['S_INFO_WINDCODE'] == stock_code]

        if len(stock_info) == 0:
            return None

        list_date = stock_info.iloc[0]['S_INFO_LISTDATE']

        if pd.isna(list_date) or list_date == '' or list_date == 'nan':
            return None

        return list_date

    def is_delisted(self, stock_code, check_date):
        """
        判断股票在指定日期是否已退市

        Args:
            stock_code: 股票代码
            check_date: 查询日期（格式：'YYYYMMDD'）

        Returns:
            bool: True表示已退市
        """
        if self.description_df is None:
            raise ValueError("请先调用load_data()加载数据")

        stock_info = self.description_df[self.description_df['S_INFO_WINDCODE'] == stock_code]

        if len(stock_info) == 0:
            return False

        delist_date = stock_info.iloc[0]['S_INFO_DELISTDATE']

        # 如果退市日期为空，说明未退市
        if pd.isna(delist_date) or delist_date == '' or delist_date == 'nan':
            return False

        # 如果查询日期>=退市日期，说明已退市
        return check_date >= delist_date

    def is_new_stock(self, stock_code, check_date, min_list_days=252):
        """
        判断股票是否为新股（上市时间不足指定天数）

        Args:
            stock_code: 股票代码
            check_date: 查询日期（格式：'YYYYMMDD'）
            min_list_days: 最少上市天数（默认252个交易日，约1年）

        Returns:
            bool: True表示是新股
        """
        list_date = self.get_list_date(stock_code)

        if list_date is None:
            # 找不到上市日期，保守起见认为是新股
            return True

        # 计算上市天数（自然日）
        try:
            list_dt = datetime.strptime(list_date, '%Y%m%d')
            check_dt = datetime.strptime(check_date, '%Y%m%d')
            days_listed = (check_dt - list_dt).days


            calendar_threshold = round(min_list_days * 365 / 252)
        except:
            return days_listed < calendar_threshold

    def filter_stocks(self, stock_list, check_date,
                     remove_st=True,
                     remove_new_stock=True,
                     min_list_days=252):
        """
        过滤股票列表

        Args:
            stock_list: 股票代码列表
            check_date: 查询日期（格式：'YYYYMMDD'）
            remove_st: 是否剔除ST股票（默认True）
            remove_new_stock: 是否剔除新股（默认True）
            min_list_days: 新股判断的最少上市天数（默认252）

        Returns:
            tuple: (过滤后的股票列表, 过滤统计信息dict)
        """
        if self.description_df is None or self.st_df is None:
            raise ValueError("请先调用load_data()加载数据")

        filtered_stocks = []
        stats = {
            'total': len(stock_list),
            'removed_no_info': 0,
            'removed_delisted': 0,
            'removed_new': 0,
            'removed_st': 0,
            'remaining': 0
        }

        for stock in stock_list:
            # 1. 检查是否有基础信息（上市日期）
            list_date = self.get_list_date(stock)
            if list_date is None:
                stats['removed_no_info'] += 1
                continue

            # 2. 检查是否已退市
            if self.is_delisted(stock, check_date):
                stats['removed_delisted'] += 1
                continue

            # 3. 检查是否为新股（上市时间不足一年）
            if remove_new_stock and self.is_new_stock(stock, check_date, min_list_days):
                stats['removed_new'] += 1
                continue

            # 4. 检查是否为ST股票
            if remove_st and self.is_st_stock(stock, check_date):
                stats['removed_st'] += 1
                continue

            filtered_stocks.append(stock)

        stats['remaining'] = len(filtered_stocks)

        return filtered_stocks, stats

    def print_filter_stats(self, stats):
        """打印过滤统计信息"""
        print(f"  过滤前: {stats['total']} 只")
        if stats['removed_no_info'] > 0:
            print(f"  无上市信息: {stats['removed_no_info']} 只")
        if stats['removed_delisted'] > 0:
            print(f"  剔除退市: {stats['removed_delisted']} 只")
        if stats['removed_new'] > 0:
            print(f"  剔除新股: {stats['removed_new']} 只")
        if stats['removed_st'] > 0:
            print(f"  剔除ST: {stats['removed_st']} 只")
        print(f"  过滤后: {stats['remaining']} 只 "
              f"(保留率: {stats['remaining']/stats['total']*100:.1f}%)")


if __name__ == '__main__':
    # 测试代码
    stock_filter = StockFilter(
        description_path='AShareDescription.xlsx',
        st_path='AShareST.xlsx'
    )
    stock_filter.load_data()

    # 典型测试案例:
    # 000013.SZ - 曾是ST (S), 2002-05-08至2004-09-20
    # 000660.SZ - 曾是*ST (Y), 2003-05-12至2004-09-13
    # 000004.SZ - 多次ST和*ST
    # 002592.SZ - 当前仍是ST (S), 2020-07-02开始，无移除日期
    test_stocks = ['000013.SZ', '000660.SZ', '000004.SZ', '002592.SZ']
    # 测试日期1: 2003-06-01 (000013是ST期间, 000660是*ST期间)
    test_date = '20030601'
    print(f"\n{'='*60}")
    print(f"测试日期: {test_date}")
    print(f"{'='*60}")
    for stock in test_stocks:
        list_date = stock_filter.get_list_date(stock)
        is_delisted = stock_filter.is_delisted(stock, test_date)
        #单独调用时有个问题就是if pd.isna(remove_dt) or remove_dt == '' or remove_dt == 'nan': return True   # 不管是否退市，一律认为"仍在ST"
        is_st = stock_filter.is_st_stock(stock, test_date)
        is_new = stock_filter.is_new_stock(stock, test_date)
        print(f"\n{stock}:")
        print(f"  上市日期: {list_date}")
        print(f"  是否退市: {is_delisted}")
        print(f"  是否ST: {is_st}")
        print(f"  是否新股: {is_new}")

    # 测试日期2: 2021-01-01 (002592是ST期间)
    test_date = '20210101'
    print(f"\n{'='*60}")
    print(f"测试日期: {test_date}")
    print(f"{'='*60}")
    for stock in test_stocks:
        is_st = stock_filter.is_st_stock(stock, test_date)
        print(f"{stock}: 是否ST = {is_st}")

    # 测试批量过滤
    print(f"\n{'='*60}")
    print(f"批量过滤测试 (日期: {test_date}):")
    print(f"{'='*60}")
    filtered, stats = stock_filter.filter_stocks(test_stocks, test_date)
    stock_filter.print_filter_stats(stats)
    print(f"过滤后股票: {filtered}")