import pandas as pd
import numpy as np


class DataLoader:
    """加载和处理因子数据"""

    def __init__(self, roe_ttm_path='roe_ttm_data.csv', peg_path='peg_data.csv', adj_close_path='adj_close.csv'):
        """
        初始化数据加载器

        Args:
            roe_ttm_path: ROE_TTM数据CSV文件路径
            peg_path: PEG数据CSV文件路径
            adj_close_path: 复权收盘价CSV文件路径（可选，用于验证）
        """
        self.roe_ttm_path = roe_ttm_path
        self.peg_path = peg_path
        self.adj_close_path = adj_close_path
        self.roe_ttm = None
        self.peg = None
        self.netprofit = None

    def load_data(self):
        """加载所有数据表"""
        print(f"正在加载数据:")
        print(f"  ROE_TTM: {self.roe_ttm_path}")
        print(f"  PEG: {self.peg_path}")

        # 加载roe_ttm数据（长格式: date, stock_id, roe_ttm）
        roe_df = pd.read_csv(self.roe_ttm_path, dtype={'date': str, 'stock_id': str})
        self.roe_ttm = roe_df.pivot(
            index='date',
            columns='stock_id',
            values='roe_ttm'
        )
        self.roe_ttm.index.name = 'date'

        # 加载peg数据（长格式: date, stock_id, peg, errorcode）
        peg_df = pd.read_csv(self.peg_path, dtype={'date': str, 'stock_id': str})
        self.peg = peg_df.pivot(
            index='date',
            columns='stock_id',
            values='peg'
        )
        self.peg.index.name = 'date'

        # netprofit暂时设为None（如果有需要可以后续添加）
        self.netprofit = None

        print(f"数据加载完成:")
        print(f"  roe_ttm: {self.roe_ttm.shape}")
        print(f"  peg: {self.peg.shape}")

        # 验证股票代码是否一致
        self._validate_stock_codes()

    def _validate_stock_codes(self):
        """
        显示各数据源的股票覆盖情况（信息性报告）

        在实际选股时会自动处理数据不一致：
        - 选股阶段：只使用roe_ttm和peg都有有效数据的股票
        - 收益计算阶段：只使用价格数据存在的股票
        """
        roe_stocks = set(self.roe_ttm.columns)
        peg_stocks = set(self.peg.columns)
        common_stocks = roe_stocks & peg_stocks

        print(f"\n数据覆盖情况:")
        print(f"  roe_ttm: {len(roe_stocks)} 只股票")
        print(f"  peg: {len(peg_stocks)} 只股票")
        print(f"  两者交集: {len(common_stocks)} 只股票")
        print(f"  说明: 选股时自动使用交集中的有效股票")

    def get_valid_stocks(self, date):
        """
        获取指定日期的有效股票及其得分

        处理流程:
        1. 取当日 roe_ttm 和 peg
        2. 剔除 peg <= 0 的股票
        3. 剔除 roe_ttm <= 0 的股票
        4. 计算 score = roe_ttm / peg

        Args:
            date: 调仓日期

        Returns:
            DataFrame: 包含stock_code, roe_ttm, peg, score列，按score降序排列
        """
        if self.roe_ttm is None or self.peg is None:
            raise ValueError("请先调用load_data()加载数据")

        # 获取当日数据
        roe_data = self.roe_ttm.loc[date]
        peg_data = self.peg.loc[date]


        # 合并为DataFrame
        df = pd.DataFrame({
            'roe_ttm': roe_data,
            'peg': peg_data
        })

        # 转换为数值类型，非数值转为NaN
        df['roe_ttm'] = pd.to_numeric(df['roe_ttm'], errors='coerce')
        df['peg'] = pd.to_numeric(df['peg'], errors='coerce')

        # 删除NaN值
        df = df.dropna()

        # 剔除peg <= 0的股票
        df = df[df['peg'] > 0]

        # 剔除roe_ttm <= 0的股票
        df = df[df['roe_ttm'] > 0]

        # 计算score = roe_ttm / peg
        df['score'] = df['roe_ttm'] / df['peg']

        # 按score降序排列
        df = df.sort_values('score', ascending=False)

        # 重置索引，将股票代码变成列
        df.reset_index(inplace=True)
        # 检查索引列的实际名称
        if df.columns[0] in ['index', 'stock_id']:
            df.rename(columns={df.columns[0]: 'stock_code'}, inplace=True)

        return df

    def get_rebalance_dates(self):
        """
        获取所有调仓日期

        Returns:
            list: 调仓日期列表
        """
        if self.roe_ttm is None:
            raise ValueError("请先调用load_data()加载数据")

        return list(self.roe_ttm.index)

    def get_top_stocks(self, date, top_n=25):
        """
        获取指定日期得分最高的前N只股票

        Args:
            date: 调仓日期
            top_n: 选择股票数量，默认25只

        Returns:
            DataFrame: 前N只股票及其数据
        """
        valid_stocks = self.get_valid_stocks(date)
        return valid_stocks.head(top_n)


if __name__ == '__main__':
    # 测试代码
    loader = DataLoader(
        roe_ttm_path='roe_ttm_data.csv',
        peg_path='peg_data.csv',
        adj_close_path='adj_close.csv'
    )
    loader.load_data()

    # 获取所有调仓日期
    dates = loader.get_rebalance_dates()
    print(f"\n调仓日期数量: {len(dates)}")
    print(f"首个调仓日: {dates[0]}")
    print(f"最后调仓日: {dates[-1]}")

    # 测试获取第一个调仓日的数据
    first_date = dates[0]
    print(f"\n{first_date} 的有效股票数据:")
    stocks_df = loader.get_valid_stocks(first_date)
    print(f"有效股票数量: {len(stocks_df)}")
    print(f"\n前10只股票:")
    print(stocks_df.head(10))

    # 测试获取得分最高的25只股票
    print(f"\n{first_date} 得分最高的25只股票:")
    top_25 = loader.get_top_stocks(first_date, top_n=25)
    print(top_25)