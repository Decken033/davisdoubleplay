import os
import pandas as pd
from iFinDPy import *
from login import login, logout
from config import USERNAME, PASSWORD

# ── 同花顺 PEG 指标候选名称（按优先级排列）──────────────────────────
# Excel 插件公式：=thsiFinD("ths_peg_lyr_stock", date, stock)
# Python 命名规则：去掉 "ths_" 前缀 + "_stock" 后缀 → peg_lyr（首选）
# peg_lyr_stock 作为兜底（极少数情况下后缀不被剥离）
PEG_INDICATOR_CANDIDATES = ["peg_lyr", "ths_peg_lyr_stock"]


def test_interface():
    """测试同花顺接口是否能正常获取 PEG 数据，并确认可用的指标名称"""
    print("=" * 50)
    print("开始测试同花顺接口 —— PEG")
    print("=" * 50)

    if not login(USERNAME, PASSWORD):
        print("登录失败，无法继续测试")
        return None  # 返回 None 表示失败

    test_stock = "000002.SZ"
    test_date  = "20091231"

    confirmed_indicator = None

    for indicator in PEG_INDICATOR_CANDIDATES:
        print(f"\n── 尝试指标名称: [{indicator}] ──────────────────────")

        try:
            result = THS_BD(test_stock, indicator, test_date)
            print(f"  errorcode={result.errorcode}, data=\n{result.data}")

            if result.errorcode == 0 and result.data is not None:
                print(f"\n  ✓ [{indicator}] 测试成功")
                confirmed_indicator = indicator
                break
            else:
                print(f"  ✗ [{indicator}] 失败 (errorcode={result.errorcode})")
        except Exception as e:
            print(f"  ✗ [{indicator}] 调用异常: {e}")

    logout()

    if confirmed_indicator is None:
        print("\n✗ 所有候选指标名称均失败，请核对同花顺 PEG 指标代码")
        return None

    print(f"\n最终确认: 指标={confirmed_indicator}")
    return confirmed_indicator


def get_peg_data(indicator: str):
    """
    获取所有股票的 PEG 数据，支持断点续传。
    当数据缺失时打印 errorcode 便于排查。

    Parameters
    ----------
    indicator : str   已确认的同花顺 PEG 指标名称，如 "peg_lyr"
    """
    print("=" * 50)
    print(f"开始批量获取 PEG 数据  (indicator={indicator})")
    print("=" * 50)

    # ── 读取股票列表 ─────────────────────────────────────────────────
    df = pd.read_csv(
        "../adj_close.csv",
        dtype={"date": str, "stock_id": str, "adj_close": float},
    )
    stock_list  = df["stock_id"].unique().tolist()
    stock_count = len(stock_list)
    print(f"共需获取 {stock_count} 只股票的数据")

    # ── 读取日期列表（复用 roe_ttm sheet 的日期轴）───────────────────
    df_dates  = pd.read_excel("../data_1.xlsx", sheet_name="roe_ttm", index_col=0)
    date_list = df_dates.index.astype(str).str.replace("-", "").tolist()
    print(f"共需获取 {len(date_list)} 个日期的数据")
    print(f"日期范围：{date_list[0]} 至 {date_list[-1]}")

    # ── 断点续传 ─────────────────────────────────────────────────────
    output_file = "../peg_data.csv"
    temp_file   = "../peg_temp.csv"

    if pd.io.common.file_exists(temp_file):
        print(f"\n发现临时文件，从断点继续...")
        existing_df = pd.read_csv(
            temp_file,
            dtype={"date": str, "stock_id": str, "peg": float, "errorcode": float},
        )
        all_data      = existing_df.to_dict("records")
        completed_set = set(zip(existing_df["date"], existing_df["stock_id"]))
        print(f"已完成 {len(completed_set)} 条记录")
    else:
        all_data      = []
        completed_set = set()

    # ── 登录 ─────────────────────────────────────────────────────────
    if not login(USERNAME, PASSWORD):
        print("登录失败，无法继续")
        return None

    total_requests = len(stock_list) * len(date_list)
    completed      = len(completed_set)
    print(f"\n开始批量获取，共需 {total_requests} 次请求...\n")

    try:
        for date in date_list:
            print(f"正在获取 {date} 的数据...")

            for stock in stock_list:
                if (date, stock) in completed_set:
                    continue

                try:
                    result = THS_BD(stock, indicator, date)

                    if result.errorcode == 0 and result.data is not None:
                        peg_value = (
                            result.data[indicator].iloc[0]
                            if len(result.data) > 0
                            else None
                        )
                        all_data.append(
                            {"date": date, "stock_id": stock, "peg": peg_value, "errorcode": 0}
                        )
                    else:
                        # ── 数据缺失时记录 errorcode ─────────────────
                        print(
                            f"  ✗ {stock} @ {date}  数据缺失  "
                            f"errorcode={result.errorcode}"
                        )
                        all_data.append(
                            {"date": date, "stock_id": stock, "peg": None, "errorcode": result.errorcode}
                        )

                    completed += 1

                    # 每 100 条保存一次临时文件
                    if completed % 100 == 0:
                        pd.DataFrame(all_data).to_csv(temp_file, index=False)
                        pct = completed / total_requests * 100
                        print(
                            f"  进度: {completed}/{total_requests} "
                            f"({pct:.1f}%) — 已保存临时文件"
                        )

                except Exception as e:
                    print(f"  ✗ {stock} @ {date}  调用异常: {e}")
                    all_data.append(
                        {"date": date, "stock_id": stock, "peg": None, "errorcode": -1}
                    )
                    completed += 1

    except KeyboardInterrupt:
        print("\n\n用户中断！正在保存临时数据...")
        pd.DataFrame(all_data).to_csv(temp_file, index=False)
        print(f"临时数据已保存到: {temp_file}")
        print("下次运行将从断点继续")
        logout()
        return None

    logout()

    # ── 汇总 & 保存 ──────────────────────────────────────────────────
    result_df = pd.DataFrame(all_data)
    print(f"\n✓ 数据获取完成！共 {len(result_df)} 条记录")
    print(f"有效数据: {result_df['peg'].notna().sum()} 条")
    print(f"缺失数据: {result_df['peg'].isna().sum()} 条")

    # ── 统计各 errorcode 的分布 ──────────────────────────────────────
    if result_df['peg'].isna().sum() > 0:
        print("\n缺失数据 errorcode 分布:")
        errorcode_counts = result_df[result_df['peg'].isna()]['errorcode'].value_counts().sort_index()
        for code, count in errorcode_counts.items():
            print(f"  errorcode {int(code)}: {count} 条")

    result_df.to_csv(output_file, index=False)
    print(f"\n数据已保存到: {output_file}")

    if os.path.exists(temp_file):
        os.remove(temp_file)
        print("临时文件已清理")

    return result_df


if __name__ == "__main__":
    outcome = test_interface()

    if outcome is None:
        print("\n接口测试失败，请检查配置、网络连接及指标名称")
    else:
        confirmed_indicator = outcome
        print("\n" + "=" * 50)
        response = input("接口测试成功！是否继续批量获取数据？(y/n): ")
        if response.strip().lower() == "y":
            get_peg_data(confirmed_indicator)
