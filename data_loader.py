import pandas as pd
import numpy as np


class DataLoader:
    """加载和处理因子数据"""

    def __init__(self, data_path='data_1.xlsx'):
        """
        初始化数据加载器

        Args:
            data_path: Excel数据文件路径
        """
        self.data_path = data_path
        self.roe_ttm = None
        self.peg = None
        self.netprofit = None

    def load_data(self):
        """加载所有数据表"""
        print(f"正在加载数据: {self.data_path}")

        # 读取所有sheet
        excel_data = pd.read_excel(self.data_path, sheet_name=None)

        # 加载roe_ttm表
        self.roe_ttm = excel_data['roe_ttm']
        self.roe_ttm.set_index(self.roe_ttm.columns[0], inplace=True)
        self.roe_ttm.index.name = 'date'

        # 加载peg表
        self.peg = excel_data['peg']
        self.peg.set_index(self.peg.columns[0], inplace=True)
        self.peg.index.name = 'date'

        # 加载netprofit表
        self.netprofit = excel_data['netprofit']
        self.netprofit.set_index(self.netprofit.columns[0], inplace=True)
        self.netprofit.index.name = 'date'

        print(f"数据加载完成:")
        print(f"  roe_ttm: {self.roe_ttm.shape}")
        print(f"  peg: {self.peg.shape}")
        print(f"  netprofit: {self.netprofit.shape}")

        # 验证股票代码是否一致
        self._validate_stock_codes()

    def _validate_stock_codes(self):
        """
        验证三个表的股票代码是否一致

        检查 roe_ttm, peg, netprofit 三个表的列（股票代码）是否完全相同
        如果不一致，打印警告信息
        """
        roe_stocks = set(self.roe_ttm.columns)
        peg_stocks = set(self.peg.columns)
        netprofit_stocks = set(self.netprofit.columns)

        # 检查 roe_ttm 和 peg 是否一致
        if roe_stocks != peg_stocks:
            only_in_roe = roe_stocks - peg_stocks
            only_in_peg = peg_stocks - roe_stocks
            print(f"\n警告：roe_ttm 和 peg 表的股票代码不一致！")
            if only_in_roe:
                print(f"  仅在 roe_ttm 中: {len(only_in_roe)} 只股票")
                print(f"  示例: {list(only_in_roe)[:5]}")
            if only_in_peg:
                print(f"  仅在 peg 中: {len(only_in_peg)} 只股票")
                print(f"  示例: {list(only_in_peg)[:5]}")

        # 检查 roe_ttm 和 netprofit 是否一致
        if roe_stocks != netprofit_stocks:
            only_in_roe = roe_stocks - netprofit_stocks
            only_in_netprofit = netprofit_stocks - roe_stocks
            print(f"\n警告：roe_ttm 和 netprofit 表的股票代码不一致！")
            if only_in_roe:
                print(f"  仅在 roe_ttm 中: {len(only_in_roe)} 只股票")
                print(f"  示例: {list(only_in_roe)[:5]}")
            if only_in_netprofit:
                print(f"  仅在 netprofit 中: {len(only_in_netprofit)} 只股票")
                print(f"  示例: {list(only_in_netprofit)[:5]}")

        # 如果三个表完全一致
        if roe_stocks == peg_stocks == netprofit_stocks:
            print(f"\n✓ 三个表的股票代码完全一致，共 {len(roe_stocks)} 只股票")
        else:
            # 计算三个表的交集
            common_stocks = roe_stocks & peg_stocks & netprofit_stocks
            print(f"\n三个表的共同股票: {len(common_stocks)} 只")

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
        df.rename(columns={'index': 'stock_code'}, inplace=True)

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
    loader = DataLoader('data_1.xlsx')
    loader.load_data()

    # 获取所有调仓日期
    dates = loader.get_rebalance_dates()
    print(f"\n调仓日期数量: {len(dates)}")
    print(f"首个调仓日: {dates[0]}")
    print(f"最后调仓日: {dates[-1]}")

    # 测试获取第一个调仓日的数据
    first_date = dates[0]
    print(f"\n{first_date} 的有效股票数据:")
    valid_stocks = loader.get_valid_stocks(first_date)
    print(f"有效股票数量: {len(valid_stocks)}")
    print(f"\n前10只股票:")
    print(valid_stocks.head(10))

    # 测试获取得分最高的25只股票
    print(f"\n{first_date} 得分最高的25只股票:")
    top_25 = loader.get_top_stocks(first_date, top_n=25)
    print(top_25)