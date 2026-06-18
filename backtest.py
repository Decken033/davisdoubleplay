import pandas as pd
import numpy as np
from data_loader import DataLoader


class FactorBacktest:
    """因子有效性回测框架"""

    def __init__(self, data_loader, price_data_path='adj_close.csv'):
        """
        初始化回测器

        Args:
            data_loader: DataLoader实例
            price_data_path: 收盘价数据路径
        """
        self.loader = data_loader
        self.price_data_path = price_data_path
        self.prices = None
        self.holdings = []  # 记录每期持仓
        self.returns = []   # 记录每期收益

    def load_prices(self):
        """加载收盘价数据"""
        print(f"正在加载收盘价数据: {self.price_data_path}")
        self.prices = pd.read_csv(
            self.price_data_path,
            dtype={'date': str, 'stock_id': str, 'adj_close': float}
        )

        # 转换为pivot表格式 (date x stock_id)
        self.prices = self.prices.pivot(
            index='date',
            columns='stock_id',
            values='adj_close'
        )

        print(f"收盘价数据加载完成: {self.prices.shape}")
        print(f"日期范围: {self.prices.index[0]} 至 {self.prices.index[-1]}")
        print(f"股票数量: {len(self.prices.columns)}")

    def get_period_return(self, stocks, start_date, end_date, min_valid_stocks=5):
        """
        计算一组股票在指定区间的收益率

        Args:
            stocks: 股票代码列表
            start_date: 开始日期（建仓日）
            end_date: 结束日期（平仓日）
            min_valid_stocks: 最少有效股票数，少于此数返回None

        Returns:
            tuple: (组合收益率, 有效股票数) 或 (None, 0)
        """
        if start_date not in self.prices.index or end_date not in self.prices.index:
            return None, 0

        # 获取开始和结束价格
        start_prices = self.prices.loc[start_date, stocks]
        end_prices = self.prices.loc[end_date, stocks]

        # 计算个股收益率
        stock_returns = (end_prices - start_prices) / start_prices

        # 剔除NaN（停牌、退市、价格数据缺失等）
        valid_returns = stock_returns.dropna()

        if len(valid_returns) < min_valid_stocks:
            return None, len(valid_returns)

        # 等权平均收益
        portfolio_return = valid_returns.mean()

        return portfolio_return, len(valid_returns)

    def get_market_return(self, start_date, end_date, min_valid_stocks=100):
        """
        计算全A平均收益率（等权）

        Args:
            start_date: 开始日期
            end_date: 结束日期
            min_valid_stocks: 最少有效股票数，少于此数返回None

        Returns:
            tuple: (市场收益率, 有效股票数) 或 (None, 0)
        """
        if start_date not in self.prices.index or end_date not in self.prices.index:
            return None, 0

        # 获取所有股票
        all_stocks = self.prices.columns.tolist()

        return self.get_period_return(all_stocks, start_date, end_date, min_valid_stocks)

    def align_date_to_trading_day(self, date):
        """
        将日期对齐到最近的交易日（向后查找）

        如果给定日期是交易日，直接返回；
        如果是非交易日（周末/节假日），返回之后最近的交易日。

        Args:
            date: 日期字符串，格式'YYYYMMDD'

        Returns:
            str: 对齐后的交易日日期，如果找不到返回None
        """
        if self.prices is None:
            raise ValueError("请先调用load_prices()加载价格数据")

        # 如果日期本身就是交易日，直接返回
        if date in self.prices.index:
            return date

        # 获取所有交易日
        trading_days = self.prices.index.tolist()

        # 向后查找最近的交易日
        for trading_day in trading_days:
            if trading_day >= date:
                return trading_day

        # 如果所有交易日都早于给定日期，返回None
        return None

    def run_backtest(self, top_n=25):
        """
        运行回测

        流程:
        1. 遍历所有调仓日
        2. 每个调仓日选出top_n只股票
        3. 持有到下个调仓日
        4. 计算区间收益
        5. 对比市场平均

        Args:
            top_n: 每期选股数量
        """
        if self.prices is None:
            raise ValueError("请先调用load_prices()加载价格数据")

        print("=" * 60)
        print(f"开始回测 —— 每期选择 {top_n} 只股票")
        print("=" * 60)

        # 获取调仓日期
        rebalance_dates = self.loader.get_rebalance_dates()
        print(f"\n原始调仓日期数量: {len(rebalance_dates)}")
        print(f"日期范围: {rebalance_dates[0]} 至 {rebalance_dates[-1]}")

        # 确保调仓日期是字符串格式
        rebalance_dates = [str(d).replace('-', '') for d in rebalance_dates]

        # 过滤掉早于价格数据最早日期的调仓日期
        price_start = self.prices.index[0]
        rebalance_dates = [d for d in rebalance_dates if d >= price_start]
        print(f"过滤后调仓日期数量: {len(rebalance_dates)} (价格数据从 {price_start} 开始)")
        if len(rebalance_dates) > 0:
            print(f"实际回测日期范围: {rebalance_dates[0]} 至 {rebalance_dates[-1]}")

        # 遍历每个调仓周期
        for i in range(len(rebalance_dates) - 1):
            factor_start_date = rebalance_dates[i]
            factor_end_date = rebalance_dates[i + 1]

            # 日期对齐到交易日
            start_date = self.align_date_to_trading_day(factor_start_date)
            end_date = self.align_date_to_trading_day(factor_end_date)

            # 检查日期对齐结果
            if start_date is None or end_date is None:
                print(f"\n── 周期 {i+1}/{len(rebalance_dates)-1}: {factor_start_date} → {factor_end_date} ──")
                print(f"  X 日期对齐失败（超出价格数据范围）")
                continue

            # 显示日期对齐信息
            align_info = ""
            if factor_start_date != start_date:
                align_info += f" (起始日 {factor_start_date}→{start_date})"
            if factor_end_date != end_date:
                align_info += f" (结束日 {factor_end_date}→{end_date})"

            print(f"\n── 周期 {i+1}/{len(rebalance_dates)-1}: {start_date} → {end_date}{align_info} ──")

            # 获取当期选股
            try:
                # 使用因子日期（未对齐）进行选股
                top_stocks = self.loader.get_top_stocks(factor_start_date, top_n=top_n)
                selected_stocks = top_stocks['stock_code'].tolist()
                print(f"  选中股票数: {len(selected_stocks)}")
            except Exception as e:
                print(f"  X 选股失败: {e}")
                continue

            # 计算组合收益
            portfolio_ret, valid_count = self.get_period_return(selected_stocks, start_date, end_date)

            # 计算市场收益
            market_ret, market_count = self.get_market_return(start_date, end_date)

            if portfolio_ret is not None and market_ret is not None:
                excess_ret = portfolio_ret - market_ret
                print(f"  组合收益: {portfolio_ret*100:7.2f}% (有效股票: {valid_count}/{len(selected_stocks)})")
                print(f"  市场收益: {market_ret*100:7.2f}% (有效股票: {market_count})")
                print(f"  超额收益: {excess_ret*100:7.2f}%")

                # 记录结果
                self.holdings.append({
                    'period': i + 1,
                    'factor_start_date': factor_start_date,
                    'factor_end_date': factor_end_date,
                    'start_date': start_date,
                    'end_date': end_date,
                    'stocks': selected_stocks,
                    'valid_stocks_count': valid_count,
                    'portfolio_return': portfolio_ret,
                    'market_return': market_ret,
                    'excess_return': excess_ret
                })
            else:
                if portfolio_ret is None:
                    print(f"  X 组合收益计算失败（有效股票不足: {valid_count}/{len(selected_stocks)}）")
                if market_ret is None:
                    print(f"  X 市场收益计算失败（有效股票不足: {market_count}）")

        # 生成回测报告
        self._generate_report()

    def _generate_report(self):
        """生成回测报告"""
        if len(self.holdings) == 0:
            print("\n没有有效的回测数据")
            return

        print("\n" + "=" * 60)
        print("回测报告")
        print("=" * 60)

        df = pd.DataFrame(self.holdings)

        # 累计收益
        cumulative_portfolio = (1 + df['portfolio_return']).prod() - 1
        cumulative_market = (1 + df['market_return']).prod() - 1
        cumulative_excess = cumulative_portfolio - cumulative_market

        print(f"\n总周期数: {len(df)}")
        print(f"\n累计收益:")
        print(f"  组合累计: {cumulative_portfolio*100:7.2f}%")
        print(f"  市场累计: {cumulative_market*100:7.2f}%")
        print(f"  累计超额: {cumulative_excess*100:7.2f}%")

        # 平均收益
        print(f"\n平均单期收益:")
        print(f"  组合平均: {df['portfolio_return'].mean()*100:7.2f}%")
        print(f"  市场平均: {df['market_return'].mean()*100:7.2f}%")
        print(f"  平均超额: {df['excess_return'].mean()*100:7.2f}%")

        # 胜率
        win_rate = (df['excess_return'] > 0).sum() / len(df)
        print(f"\n胜率（超额收益>0）: {win_rate*100:.1f}%")

        # 波动率
        portfolio_std = df['portfolio_return'].std()
        market_std = df['market_return'].std()
        print(f"\n收益波动率:")
        print(f"  组合波动: {portfolio_std*100:7.2f}%")
        print(f"  市场波动: {market_std*100:7.2f}%")

        # 夏普比率（简化版，假设无风险利率为0）
        sharpe_portfolio = df['portfolio_return'].mean() / portfolio_std if portfolio_std > 0 else 0
        sharpe_market = df['market_return'].mean() / market_std if market_std > 0 else 0
        print(f"\n夏普比率（年化需乘调仓频率）:")
        print(f"  组合夏普: {sharpe_portfolio:.3f}")
        print(f"  市场夏普: {sharpe_market:.3f}")

        # 最大回撤
        cumret_portfolio = (1 + df['portfolio_return']).cumprod()
        cumret_market = (1 + df['market_return']).cumprod()

        running_max_portfolio = cumret_portfolio.cummax()
        running_max_market = cumret_market.cummax()

        drawdown_portfolio = (cumret_portfolio - running_max_portfolio) / running_max_portfolio
        drawdown_market = (cumret_market - running_max_market) / running_max_market

        max_dd_portfolio = drawdown_portfolio.min()
        max_dd_market = drawdown_market.min()

        print(f"\n最大回撤:")
        print(f"  组合最大回撤: {max_dd_portfolio*100:7.2f}%")
        print(f"  市场最大回撤: {max_dd_market*100:7.2f}%")

        # 保存详细结果
        output_file = 'backtest_results.csv'
        df.to_csv(output_file, index=False)
        print(f"\n详细结果已保存到: {output_file}")

    def get_results_df(self):
        """返回回测结果DataFrame"""
        return pd.DataFrame(self.holdings)


if __name__ == '__main__':
    # 加载数据
    print("步骤 1: 加载因子数据")
    loader = DataLoader(
        roe_ttm_path='roe_ttm_data.csv',
        peg_path='peg_data.csv',
        adj_close_path='adj_close.csv'
    )
    loader.load_data()

    # 初始化回测
    print("\n步骤 2: 初始化回测器")
    backtest = FactorBacktest(loader, price_data_path='adj_close.csv')
    backtest.load_prices()

    # 运行回测
    print("\n步骤 3: 运行回测")
    backtest.run_backtest(top_n=25)