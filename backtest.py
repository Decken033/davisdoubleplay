import pandas as pd
import numpy as np
from data_loader import DataLoader
from factor_engine import StockSelector


class FactorBacktest:
    """因子有效性回测框架"""

    def __init__(self, data_loader, price_data_path='adj_close.csv',
                 benchmark_path='000905benchmark_comparison.xlsx',
                 start_date='20100101', end_date='20170531',
                 buy_cost=0.001, sell_cost=0.002, max_weight=0.10):
        """
        初始化回测器

        Args:
            data_loader: DataLoader实例
            price_data_path: 收盘价数据路径
            benchmark_path: 中证500指数数据路径
            start_date: 回测起始日期 (YYYYMMDD格式)
            end_date: 回测结束日期 (YYYYMMDD格式)
            buy_cost: 买入成本比例 (默认0.1%)
            sell_cost: 卖出成本比例 (默认0.2%)
            max_weight: 单只股票最大权重 (默认10%)
        """
        self.loader = data_loader
        self.price_data_path = price_data_path
        self.benchmark_path = benchmark_path
        self.start_date = start_date
        self.end_date = end_date
        self.buy_cost = buy_cost
        self.sell_cost = sell_cost
        self.max_weight = max_weight

        self.prices = None  # 价格数据 (date × stock_id)
        self.benchmark = None  # 中证500指数数据 (date × close)
        self.holdings = []  # 持仓记录
        self.previous_portfolio = {}  # 上一期持仓 {股票代码: 权重}

        # 初始化选股器
        self.selector = StockSelector(data_loader)

    def load_prices(self):
        """加载价格数据和基准数据"""
        print("\n正在加载价格数据...")
        # 直接使用DataLoader中已加载的价格数据
        self.prices = self.loader.adj_close.copy()
        print(f"价格数据: {self.prices.shape}")

        # 加载中证500指数数据
        print(f"\n正在加载中证500基准数据: {self.benchmark_path}")
        benchmark_df = pd.read_excel(self.benchmark_path)
        benchmark_df.columns = ['date', 'close', 'benchmark_value']
        benchmark_df['date'] = pd.to_datetime(benchmark_df['date']).dt.strftime('%Y%m%d')
        benchmark_df = benchmark_df.set_index('date')
        self.benchmark = benchmark_df['close']
        print(f"基准数据: {len(self.benchmark)} 条记录")
        print(f"基准日期范围: {self.benchmark.index.min()} 至 {self.benchmark.index.max()}")

        # 初始化选股器的季度数据
        self.selector.calculate_quarterly_data()





    def run_backtest(self, top_n=25):
        """
        运行回测

        流程:
        1. 遍历所有调仓日
        2. 每个调仓日选出top_n只股票
        3. 持有到下个调仓日
        4. 计算区间收益
        5. 对比中证500指数

        Args:
            top_n: 每期选择的股票数量
        """
        if self.prices is None:
            raise ValueError("请先调用load_prices()加载价格数据")

        # 获取所有调仓日期，并过滤到指定时间范围
        all_rebalance_dates = self.loader.get_rebalance_dates()
        rebalance_dates = [
            d for d in all_rebalance_dates
            if self.start_date <= d <= self.end_date
        ]
        print(f"\n回测时间范围: {self.start_date} 至 {self.end_date}")
        print(f"回测期间调仓日数量: {len(rebalance_dates)}")
        print(f"交易成本: 买入{self.buy_cost*100:.1f}%, 卖出{self.sell_cost*100:.1f}%")
        print(f"单只股票权重上限: {self.max_weight*100:.1f}%")

        for i in range(len(rebalance_dates) - 1):
            current_date = rebalance_dates[i]
            next_date = rebalance_dates[i + 1]

            print(f"\n{'='*60}")
            print(f"周期 {i+1}/{len(rebalance_dates)-1}: {current_date} -> {next_date}")
            print(f"{'='*60}")

            # 选股
            selected_stocks = self.selector.get_top_stocks(current_date, top_n=top_n)

            # 即使选不出股票，也继续处理

            # 计算组合收益（包含交易成本和权重限制）
            result = self._calculate_portfolio_return_with_costs(
                selected_stocks, current_date, next_date
            )
            portfolio_return = result['portfolio_return']
            actual_position = result['actual_position']
            actual_position_pct = result['actual_position_pct']
            current_portfolio = result['portfolio_weights']  # 获取权重字典

            # 计算基准收益（中证500）
            benchmark_return = self._calculate_benchmark_return(current_date, next_date)

            # 记录持仓
            self.holdings.append({
                'rebalance_date': current_date,
                'next_date': next_date,
                'num_stocks': len(selected_stocks),
                'actual_position': len(actual_position),
                'position_pct': actual_position_pct,
                'portfolio_return': portfolio_return,
                'benchmark_return': benchmark_return,  # 基准指数的真实收益率
                'excess_return': portfolio_return - benchmark_return * actual_position_pct
            })

            print(f"\n  目标股票数: {len(selected_stocks)}")
            print(f"  实际持仓数: {len(actual_position)}")
            print(f"  实际仓位: {actual_position_pct*100:.1f}%")
            print(f"  组合收益: {portfolio_return*100:7.2f}%")
            print(f"  基准收益: {benchmark_return*100:7.2f}%")
            print(f"  调整后基准: {(benchmark_return * actual_position_pct)*100:7.2f}%")
            print(f"  超额收益: {(portfolio_return - benchmark_return * actual_position_pct)*100:7.2f}%")

            # 更新上一期持仓（使用函数返回的权重字典）
            self.previous_portfolio = current_portfolio

        # 生成回测报告
        self._generate_report()

    def _calculate_portfolio_return_with_costs(self, stocks, start_date, end_date):
        """
        计算组合收益率（考虑交易成本和权重限制）

        交易规则：
        - 在start_date时点进行调仓交易
        - 卖出上期持有但本期不要的股票（扣除卖出成本）
        - 买入本期选中但上期没有的股票（扣除买入成本）
        - 继续持有两期都有的股票：
          * 如果权重需要调整（增仓/减仓），扣除对应的买入/卖出成本
          * 如果权重不变，零交易成本
        - 从start_date持有到end_date，计算持有期收益

        注意：
        - 价格缺失（停牌等）的股票会被跳过，不计入实际持仓
        - 如果是continuing股票停牌，相当于被动清仓（扣除卖出成本）

        Args:
            stocks: 本期选中的股票代码列表
            start_date: 起始日期（调仓日）
            end_date: 结束日期（下次调仓日）

        Returns:
            dict: {
                'portfolio_return': 组合收益率,
                'actual_position': 实际持仓列表,
                'actual_position_pct': 实际仓位比例,
                'portfolio_weights': {股票代码: 权重} 字典
            }
        """
        # 对stocks去重
        stocks = list(dict.fromkeys(stocks))  # 保持顺序的去重

        # 日期对齐：将调仓日期对齐到实际交易日
        aligned_start_date = self.loader.align_to_trading_date(start_date)
        aligned_end_date = self.loader.align_to_trading_date(end_date)

        # 如果日期对齐失败，跳过本期
        if aligned_start_date is None or aligned_end_date is None:
            print(f"   警告：无法对齐日期 ({start_date} 或 {end_date})，跳过本期")
            # 返回空仓，但需要处理上期清仓成本
            if len(self.previous_portfolio) > 0:
                prev_total_weight = sum(self.previous_portfolio.values())
                return {
                    'portfolio_return': -prev_total_weight * self.sell_cost,
                    'actual_position': [],
                    'actual_position_pct': 0.0,
                    'portfolio_weights': {}
                }
            else:
                return {
                    'portfolio_return': 0.0,
                    'actual_position': [],
                    'actual_position_pct': 0.0,
                    'portfolio_weights': {}
                }

        # 使用对齐后的日期
        start_date = aligned_start_date
        end_date = aligned_end_date

        # 计算每只股票的权重（考虑权重上限）
        n_stocks = len(stocks)
        if n_stocks == 0:
            # 空仓情况：如果上期有持仓，需要扣除卖出成本
            if len(self.previous_portfolio) > 0:
                # 计算上期实际总权重
                prev_total_weight = sum(self.previous_portfolio.values())
                # 全部清仓，卖出成本 = 上期总权重 × 卖出费率
                return {
                    'portfolio_return': -prev_total_weight * self.sell_cost,
                    'actual_position': [],
                    'actual_position_pct': 0.0,
                    'portfolio_weights': {}
                }
            else:
                return {
                    'portfolio_return': 0.0,
                    'actual_position': [],
                    'actual_position_pct': 0.0,
                    'portfolio_weights': {}
                }

        # 等权重计算
        equal_weight = 1.0 / n_stocks

        # 如果等权重超过上限，则使用上限权重，剩余资金保持现金
        if equal_weight > self.max_weight:
            # 触发条件：n_stocks < 1/max_weight，此时 n_stocks < 10
            # 所以不需要截断，selected_stocks 本身就少于 10 只
            target_weight = self.max_weight
            selected_stocks = stocks
            # 剩余资金保持现金，不再分配
            # 例如：8只股票 × 10% = 80%仓位，剩余20%现金
        else:
            # 股票数 ≥ 10，等权自然满足单票 ≤ 10%
            target_weight = equal_weight
            selected_stocks = stocks

        # 第一步：计算实际持有期收益和有效持仓
        # 先确定哪些股票真的能交易
        returns = []
        actual_position = []
        weights = []

        for stock in selected_stocks:
            # 检查股票在价格数据中是否存在
            if stock not in self.prices.columns:
                continue

            start_price = self.prices.loc[start_date, stock]
            end_price = self.prices.loc[end_date, stock]

            # 跳过价格缺失的情况
            # 如果是continuing股票停牌，会被排除在actual_position外，
            # 从而在后续交易成本计算时被归入to_sell，支付卖出成本
            if pd.isna(start_price) or pd.isna(end_price) or start_price <= 0:
                continue

            # 计算持有期收益（不含交易成本）
            stock_return = (end_price - start_price) / start_price

            returns.append(stock_return)
            actual_position.append(stock)
            weights.append(target_weight)

        # 如果没有有效持仓
        if len(returns) == 0:
            # 即使没有买入成功，上期持仓的清仓成本还是要扣的
            if len(self.previous_portfolio) > 0:
                # 计算上期实际总权重
                prev_total_weight = sum(self.previous_portfolio.values())
                # 全部清仓，卖出成本 = 上期总权重 × 卖出费率
                return {
                    'portfolio_return': -prev_total_weight * self.sell_cost,
                    'actual_position': [],
                    'actual_position_pct': 0.0,
                    'portfolio_weights': {}
                }
            else:
                return {
                    'portfolio_return': 0.0,
                    'actual_position': [],
                    'actual_position_pct': 0.0,
                    'portfolio_weights': {}
                }

        # 第二步：计算调仓交易成本（基于实际可交易的股票和真实权重）
        previous_set = set(self.previous_portfolio.keys())
        current_set = set(actual_position)  # 使用实际成交的股票

        to_sell = previous_set - current_set  # 需要完全卖出
        to_buy = current_set - previous_set   # 需要新买入
        continuing = previous_set & current_set  # 两期都持有

        # 计算调仓成本
        turnover_cost = 0.0

        # 计算continuing股票的仓位调整成本
        for stock in continuing:
            prev_weight = self.previous_portfolio[stock]
            current_weight = target_weight
            weight_change = current_weight - prev_weight

            if weight_change > 0:
                # 增仓：买入成本
                turnover_cost += weight_change * self.buy_cost
            elif weight_change < 0:
                # 减仓：卖出成本
                turnover_cost += abs(weight_change) * self.sell_cost
            # weight_change == 0 时无交易成本

        # 完全卖出的成本：基于上期真实权重
        # 只对在调仓日有有效价格的股票计算卖出成本（停牌股票无法卖出）
        if len(to_sell) > 0:
            sell_weight = 0.0
            for stock in to_sell:
                # 检查股票在调仓日（start_date）是否可交易
                if stock in self.prices.columns:
                    start_price = self.prices.loc[start_date, stock]
                    # 只要start_date有有效价格，就能卖出
                    # 不需要检查end_date，因为卖出发生在start_date
                    if not pd.isna(start_price) and start_price > 0:
                        sell_weight += self.previous_portfolio[stock]
                    # start_date停牌：无法卖出，不扣成本（被动持有）
                else:
                    # 股票已退市或不在价格数据中：假设能按上期价格清仓
                    sell_weight += self.previous_portfolio[stock]
            turnover_cost += sell_weight * self.sell_cost

        # 新买入的成本：基于本期实际成交的真实权重
        buy_weight = len(to_buy) * target_weight
        turnover_cost += buy_weight * self.buy_cost

        # 第三步：计算组合收益

        # 不归一化权重！保持真实权重以体现现金部分
        # 例如：8只股票 × 10% = 80%，剩余20%现金
        total_weight = sum(weights)

        # 股票仓位的加权平均收益
        stock_holding_return = sum(r * w for r, w in zip(returns, weights))

        # 现金部分收益为0
        cash_weight = 1.0 - total_weight
        cash_return = 0.0


        portfolio_holding_return = stock_holding_return + cash_weight * cash_return
        portfolio_return = portfolio_holding_return - turnover_cost

        # 返回完整的权重字典
        portfolio_weights = {stock: target_weight for stock in actual_position}

        return {
            'portfolio_return': portfolio_return,
            'actual_position': actual_position,
            'actual_position_pct': total_weight,
            'portfolio_weights': portfolio_weights
        }

    def _calculate_benchmark_return(self, start_date, end_date):
        """
        计算中证500基准收益率

        Args:
            start_date: 起始日期
            end_date: 结束日期

        Returns:
            float: 基准收益率
        """
        if self.benchmark is None:
            return 0.0

        # 使用统一的日期对齐方法
        aligned_start_date = self.loader.align_to_trading_date(start_date)
        aligned_end_date = self.loader.align_to_trading_date(end_date)

        # 如果日期对齐失败，返回0
        if aligned_start_date is None or aligned_end_date is None:
            return 0.0

        # 使用对齐后的日期
        start_date = aligned_start_date
        end_date = aligned_end_date

        # 检查日期是否在基准数据中
        if start_date not in self.benchmark.index or end_date not in self.benchmark.index:
            # 尝试找到最近的日期（向前查找，保持与组合持有期一致）
            available_dates = sorted(self.benchmark.index)

            # 找到不晚于start_date的最近日期
            start_candidates = [d for d in available_dates if d <= start_date]
            if len(start_candidates) == 0:
                return 0.0
            actual_start = start_candidates[-1]

            # 找到不晚于end_date的最近日期
            end_candidates = [d for d in available_dates if d <= end_date]
            if len(end_candidates) == 0:
                return 0.0
            actual_end = end_candidates[-1]
        else:
            actual_start = start_date
            actual_end = end_date

        start_value = self.benchmark[actual_start]
        end_value = self.benchmark[actual_end]

        if pd.isna(start_value) or pd.isna(end_value) or start_value <= 0:
            return 0.0

        return (end_value - start_value) / start_value



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
        cumulative_benchmark = (1 + df['benchmark_return']).prod() - 1

        # 累计超额收益：策略和基准各自复利，最后比较净值差异
        # 计算调整后的基准累计收益（每期按实际仓位调整）
        cumulative_benchmark_adjusted = (1 + df['benchmark_return'] * df['position_pct']).prod() - 1
        cumulative_excess = cumulative_portfolio - cumulative_benchmark_adjusted

        # 计算年化收益率
        # 计算回测期间的实际年数
        start_date_dt = pd.to_datetime(self.start_date, format='%Y%m%d')
        end_date_dt = pd.to_datetime(self.end_date, format='%Y%m%d')
        years = (end_date_dt - start_date_dt).days / 365.25

        if years > 0:
            annual_return_portfolio = (1 + cumulative_portfolio) ** (1/years) - 1
            annual_return_benchmark = (1 + cumulative_benchmark) ** (1/years) - 1
            # 年化超额收益：策略年化 - 调整后基准年化
            benchmark_adjusted_annual = (1 + cumulative_benchmark_adjusted) ** (1/years) - 1
            annual_return_excess = annual_return_portfolio - benchmark_adjusted_annual
        else:
            annual_return_portfolio = 0.0
            annual_return_benchmark = 0.0
            annual_return_excess = 0.0

        print(f"\n回测期间: {self.start_date} 至 {self.end_date} ({years:.2f} 年)")
        print(f"总周期数: {len(df)}")
        print(f"交易成本: 买入{self.buy_cost*100:.1f}%, 卖出{self.sell_cost*100:.1f}%")
        print(f"单只股票权重上限: {self.max_weight*100:.1f}%")

        print(f"\n累计收益:")
        print(f"  组合累计: {cumulative_portfolio*100:7.2f}%")
        print(f"  基准累计 (中证500): {cumulative_benchmark*100:7.2f}%")
        print(f"  累计超额: {cumulative_excess*100:7.2f}%")

        print(f"\n年化收益:")
        print(f"  组合年化: {annual_return_portfolio*100:7.2f}%")
        print(f"  基准年化: {annual_return_benchmark*100:7.2f}%")
        print(f"  年化超额: {annual_return_excess*100:7.2f}%")

        # 平均收益
        print(f"\n平均单期收益:")
        print(f"  组合平均: {df['portfolio_return'].mean()*100:7.2f}%")
        print(f"  基准平均: {df['benchmark_return'].mean()*100:7.2f}%")
        print(f"  平均超额: {df['excess_return'].mean()*100:7.2f}%")

        # 平均仓位
        print(f"\n平均仓位:")
        print(f"  平均实际仓位: {df['position_pct'].mean()*100:7.1f}%")

        # 胜率
        win_rate = (df['excess_return'] > 0).sum() / len(df)
        print(f"\n胜率（超额收益>0）: {win_rate*100:.1f}%")

        # 波动率（年化）
        portfolio_std = df['portfolio_return'].std()
        benchmark_std = df['benchmark_return'].std()
        # 假设季度调仓，年化波动率 = 单期波动率 × sqrt(4)
        periods_per_year = 4  # 季度调仓
        annual_vol_portfolio = portfolio_std * np.sqrt(periods_per_year)
        annual_vol_benchmark = benchmark_std * np.sqrt(periods_per_year)

        print(f"\n收益波动率:")
        print(f"  组合波动 (单期): {portfolio_std*100:7.2f}%")
        print(f"  基准波动 (单期): {benchmark_std*100:7.2f}%")
        print(f"  组合波动 (年化): {annual_vol_portfolio*100:7.2f}%")
        print(f"  基准波动 (年化): {annual_vol_benchmark*100:7.2f}%")

        # 夏普比率（年化）
        if annual_vol_portfolio > 0:
            sharpe_portfolio = annual_return_portfolio / annual_vol_portfolio
        else:
            sharpe_portfolio = 0

        if annual_vol_benchmark > 0:
            sharpe_benchmark = annual_return_benchmark / annual_vol_benchmark
        else:
            sharpe_benchmark = 0

        print(f"\n夏普比率（年化，假设无风险利率为0）:")
        print(f"  组合夏普: {sharpe_portfolio:.3f}")
        print(f"  基准夏普: {sharpe_benchmark:.3f}")

        # 最大回撤
        cumret_portfolio = (1 + df['portfolio_return']).cumprod()
        cumret_benchmark = (1 + df['benchmark_return']).cumprod()

        running_max_portfolio = cumret_portfolio.cummax()
        running_max_benchmark = cumret_benchmark.cummax()

        drawdown_portfolio = (cumret_portfolio - running_max_portfolio) / running_max_portfolio
        drawdown_benchmark = (cumret_benchmark - running_max_benchmark) / running_max_benchmark

        max_dd_portfolio = drawdown_portfolio.min()
        max_dd_benchmark = drawdown_benchmark.min()

        print(f"\n最大回撤:")
        print(f"  组合最大回撤: {max_dd_portfolio*100:7.2f}%")
        print(f"  基准最大回撤: {max_dd_benchmark*100:7.2f}%")

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

    # 初始化回测
    print("\n步骤 2: 初始化回测器")
    backtest = FactorBacktest(
        loader,
        price_data_path='adj_close.csv',
        benchmark_path='000905benchmark_comparison.xlsx',
        start_date='20100101',
        end_date='20170531',
        buy_cost=0.001,
        sell_cost=0.002,
        max_weight=0.10
    )
    backtest.load_prices()

    # 运行回测
    print("\n步骤 3: 运行回测")
    backtest.run_backtest(top_n=25)