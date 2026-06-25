import pandas as pd
import numpy as np
from stock_filter import StockFilter


class DataLoader:
    """加载和处理因子数据"""

    def __init__(self, adj_close_path='adj_close.csv', pe_ttm_path='pe_ttm_data.csv',
                 net_profit_path='AShareIncome_Q.csv', oper_rev_path='AShareIncome_Q.csv',
                 report_date_path='AShareIssuingDatePredict.csv',
                 actual_disclosure_date_path='AShareIssuingDatePredict.csv',
                 use_stock_filter=True, description_path='AShareDescription.xlsx', st_path='AShareST.xlsx'):
        """
        初始化数据加载器

        Args:
            adj_close_path: 复权收盘价CSV文件路径
            pe_ttm_path: PE_TTM数据CSV文件路径
            net_profit_path: 归母净利润数据CSV文件路径
            oper_rev_path: 营业收入数据CSV文件路径
            report_date_path: 报告期CSV文件路径（包含stock_id, date字段）
            actual_disclosure_date_path: 实际披露日期CSV文件路径（包含stock_id, date, issuing_date字段）
            use_stock_filter: 是否使用股票过滤器（默认True）
            description_path: 上市日期数据路径
            st_path: ST状态数据路径
        """
        self.adj_close_path = adj_close_path
        self.pe_ttm_path = pe_ttm_path
        self.net_profit_path = net_profit_path
        self.oper_rev_path = oper_rev_path
        self.report_date_path = report_date_path
        self.actual_disclosure_date_path = actual_disclosure_date_path

        # 数据容器
        self.adj_close = None
        self.pe_ttm = None
        self.net_profit = None
        self.oper_rev = None
        self.report_dates = None  # DataFrame: stock_id, date(报告期), issuing_date(实际披露日期)

        self.use_stock_filter = use_stock_filter
        self.stock_filter = None

        # 初始化股票过滤器
        if use_stock_filter:
            self.stock_filter = StockFilter(description_path, st_path)

    def load_data(self):
        """加载所有数据表"""
        print(f"正在加载数据:")
        print(f"  收盘价: {self.adj_close_path}")
        print(f"  PE_TTM: {self.pe_ttm_path}")
        print(f"  归母净利润: {self.net_profit_path}")
        print(f"  营业收入: {self.oper_rev_path}")
        print(f"  报告期: {self.report_date_path}")
        print(f"  实际披露日期: {self.actual_disclosure_date_path}")

        # 加载收盘价数据（长格式: date, stock_id, adj_close）
        adj_close_df = pd.read_csv(self.adj_close_path, dtype={'date': str, 'stock_id': str})
        self.adj_close = adj_close_df.pivot(
            index='date',
            columns='stock_id',
            values='adj_close'
        )
        self.adj_close.index.name = 'date'

        # 加载pe_ttm数据（长格式: rebalance_date, pe_date, stock_id, pe_ttm）
        pe_df = pd.read_csv(self.pe_ttm_path, dtype={'rebalance_date': str, 'stock_id': str})
        # 使用rebalance_date作为索引
        self.pe_ttm = pe_df.pivot(
            index='rebalance_date',
            columns='stock_id',
            values='pe_ttm'
        )
        self.pe_ttm.index.name = 'date'

        # 加载财务数据（长格式: stock_id, date, oper_rev, net_profit）
        financial_df = pd.read_csv(self.net_profit_path, dtype={'stock_id': str, 'date': str})

        # 分别转换为宽表
        self.net_profit = financial_df.pivot(
            index='date',
            columns='stock_id',
            values='net_profit'
        )
        self.net_profit.index.name = 'date'

        self.oper_rev = financial_df.pivot(
            index='date',
            columns='stock_id',
            values='oper_rev'
        )
        self.oper_rev.index.name = 'date'

        # 加载报告期和披露日期数据（长格式: stock_id, date(报告期), issuing_date(披露日期)）
        # 注意：虽然有两个参数，但实际上这两个文件通常是同一个文件
        self.report_dates = pd.read_csv(
            self.actual_disclosure_date_path,
            dtype={'stock_id': str, 'date': str, 'issuing_date': str}
        )

        print(f"\n数据加载完成:")
        print(f"  adj_close: {self.adj_close.shape}")
        print(f"  pe_ttm: {self.pe_ttm.shape}")
        print(f"  net_profit: {self.net_profit.shape}")
        print(f"  oper_rev: {self.oper_rev.shape}")
        print(f"  report_dates: {len(self.report_dates)} 条记录")

        # 加载股票过滤器数据
        if self.use_stock_filter and self.stock_filter:
            print(f"\n正在加载股票过滤器数据:")
            self.stock_filter.load_data()

        # 验证股票代码是否一致
        self._validate_stock_codes()

    def _validate_stock_codes(self):
        """
        显示各数据源的股票覆盖情况（信息性报告）

        在实际选股时会自动处理数据不一致：
        - 选股阶段：只使用各因子都有有效数据的股票
        - 收益计算阶段：只使用价格数据存在的股票
        """
        price_stocks = set(self.adj_close.columns)
        pe_stocks = set(self.pe_ttm.columns)
        profit_stocks = set(self.net_profit.columns)
        rev_stocks = set(self.oper_rev.columns)
        report_stocks = set(self.report_dates['stock_id'].unique())

        common_stocks = price_stocks & pe_stocks & profit_stocks & rev_stocks

        print(f"\n数据覆盖情况:")
        print(f"  adj_close: {len(price_stocks)} 只股票")
        print(f"  pe_ttm: {len(pe_stocks)} 只股票")
        print(f"  net_profit: {len(profit_stocks)} 只股票")
        print(f"  oper_rev: {len(rev_stocks)} 只股票")
        print(f"  report_dates: {len(report_stocks)} 只股票")
        print(f"  全部交集: {len(common_stocks)} 只股票")
        print(f"  说明: 选股时自动使用交集中的有效股票")

    def get_available_financial_data(self, stock_id, as_of_date):
        """
        获取指定日期前已披露的最新财务数据

        Args:
            stock_id: 股票代码
            as_of_date: 查询日期（格式：'YYYYMMDD'）

        Returns:
            dict: 包含report_date(报告期), issuing_date(披露日期), net_profit, oper_rev的字典，如果没有返回None
        """
        if self.report_dates is None:
            raise ValueError("请先调用load_data()加载数据")

        # 筛选该股票在as_of_date之前已披露的数据
        stock_reports = self.report_dates[
            (self.report_dates['stock_id'] == stock_id) &
            (self.report_dates['issuing_date'] <= as_of_date)
        ]

        if len(stock_reports) == 0:
            return None

        # 取最新的报告期
        latest_report = stock_reports.sort_values('date', ascending=False).iloc[0]
        report_date = latest_report['date']
        issuing_date = latest_report['issuing_date']

        # 获取对应的财务数据
        net_profit = None
        oper_rev = None

        if report_date in self.net_profit.index and stock_id in self.net_profit.columns:
            net_profit = self.net_profit.loc[report_date, stock_id]

        if report_date in self.oper_rev.index and stock_id in self.oper_rev.columns:
            oper_rev = self.oper_rev.loc[report_date, stock_id]

        return {
            'report_date': report_date,
            'issuing_date': issuing_date,
            'net_profit': net_profit,
            'oper_rev': oper_rev
        }

    def get_rebalance_dates(self):
        """
        获取所有调仓日期

        Returns:
            list: 调仓日期列表
        """
        if self.pe_ttm is None:
            raise ValueError("请先调用load_data()加载数据")

        return list(self.pe_ttm.index)


if __name__ == '__main__':
    # 测试代码
    loader = DataLoader(
        adj_close_path='adj_close.csv',
        pe_ttm_path='pe_ttm_data.csv',
        net_profit_path='AShareIncome_Q.csv',
        oper_rev_path='AShareIncome_Q.csv',
        report_date_path='AShareIssuingDatePredict.csv',
        actual_disclosure_date_path='AShareIssuingDatePredict.csv'
    )
    loader.load_data()

    # 显示调仓日期
    dates = loader.get_rebalance_dates()
    print(f"\n调仓日期数量: {len(dates)}")
    print(f"首个调仓日: {dates[0]}")
    print(f"最后调仓日: {dates[-1]}")

    # 测试获取某个股票的可用财务数据
    test_stock = '600289.SH'
    test_date = '20101022'
    print(f"\n测试获取 {test_stock} 在 {test_date} 前的可用财务数据:")
    financial_data = loader.get_available_financial_data(test_stock, test_date)
    if financial_data:
        print(f"  报告期: {financial_data['report_date']}")
        print(f"  披露日期: {financial_data['issuing_date']}")
        print(f"  归母净利润: {financial_data['net_profit']}")
        print(f"  营业收入: {financial_data['oper_rev']}")
    else:
        print(f"  无可用数据")