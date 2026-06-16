import pandas as pd
from iFinDPy import *
from login import login, logout
from config import USERNAME, PASSWORD


def test_interface():
    """测试同花顺接口是否能正常获取ROE TTM数据"""
    print("=" * 50)
    print("开始测试同花顺接口")
    print("=" * 50)

    if not login(USERNAME, PASSWORD):
        print("登录失败，无法继续测试")
        return False

    # 测试单个股票单个日期
    test_stock = "000425.SZ"
    test_date = "20101231"

    print(f"\n测试获取股票 {test_stock} 在 {test_date} 的 ROE TTM 数据...")

    try:
        # 尝试不同的参数组合
        test_configs = [
            ('THS_BD with params', lambda: THS_BD(test_stock, 'roe_ttm', 'format:xml', test_date)),
            ('THS_BD simple', lambda: THS_BD(test_stock, 'roe_ttm', test_date)),
            ('THS_DS time series', lambda: THS_DS(test_stock, 'roe_ttm', test_date, test_date)),
            ('THS_HF high frequency', lambda: THS_HF(test_stock, 'roe_ttm', test_date, '')),
        ]

        result = None
        for func_name, func_call in test_configs:
            try:
                print(f"\n尝试: {func_name}")
                result = func_call()
                print(f"  errorcode: {result.errorcode}")
                print(f"  errmsg: {result.errmsg}")
                print(f"  data: {result.data}")

                # 查看对象的所有属性
                print(f"  对象属性: {[attr for attr in dir(result) if not attr.startswith('_')]}")

                if result.errorcode == 0 and result.data is not None:
                    print(f"  ✓ 成功获取数据！")
                    logout()
                    return True

            except NameError as ne:
                print(f"  ✗ 函数不存在")
            except TypeError as te:
                print(f"  ✗ 参数错误: {te}")
            except Exception as e:
                print(f"  ✗ 出错: {e}")

        logout()
        print("\n所有尝试都失败了，请检查同花顺 API 文档")
        return False

    except Exception as e:
        print(f"✗ 整体出错：{e}")
        logout()
        return False


def get_roe_ttm_data():
    """获取所有股票的ROE TTM数据"""
    print("=" * 50)
    print("开始获取ROE TTM数据")
    print("=" * 50)

    # 读取股票代码
    df = pd.read_csv(
        "../adj_close.csv",
        dtype={
            "date": str,
            "stock_id": str,
            "adj_close": float,
        }
    )
    stock_list = df["stock_id"].unique().tolist()
    stock_count = len(stock_list)
    print(f"共需获取 {stock_count} 只股票的数据")

    # 读取日期列表
    df_dates = pd.read_excel("../data_1.xlsx", sheet_name="roe_ttm", index_col=0)
    date_list = df_dates.index.astype(str).str.replace('-', '').tolist()
    print(f"共需获取 {len(date_list)} 个日期的数据")
    print(f"日期范围：{date_list[0]} 至 {date_list[-1]}")

    # 登录
    if not login(USERNAME, PASSWORD):
        print("登录失败，无法继续")
        return None

    # 批量获取数据
    all_data = []
    total_requests = len(stock_list) * len(date_list)
    completed = 0

    print(f"\n开始批量获取，共需 {total_requests} 次请求...\n")

    for date in date_list:
        print(f"正在获取 {date} 的数据...")

        for stock in stock_list:
            try:
                result = THS_BD(stock, 'roe_ttm', date)

                if result.errorcode == 0 and result.data is not None:
                    # 提取数据
                    roe_value = result.data['roe_ttm'].iloc[0] if len(result.data) > 0 else None
                    all_data.append({
                        'date': date,
                        'stock_id': stock,
                        'roe_ttm': roe_value
                    })
                else:
                    all_data.append({
                        'date': date,
                        'stock_id': stock,
                        'roe_ttm': None
                    })

                completed += 1
                if completed % 100 == 0:
                    print(f"  进度: {completed}/{total_requests} ({completed/total_requests*100:.1f}%)")

            except Exception as e:
                print(f"  ✗ 获取 {stock} 在 {date} 的数据失败: {e}")
                all_data.append({
                    'date': date,
                    'stock_id': stock,
                    'roe_ttm': None
                })
                completed += 1

    logout()

    # 转换为 DataFrame
    result_df = pd.DataFrame(all_data)
    print(f"\n✓ 数据获取完成！共 {len(result_df)} 条记录")
    print(f"有效数据: {result_df['roe_ttm'].notna().sum()} 条")
    print(f"缺失数据: {result_df['roe_ttm'].isna().sum()} 条")

    # 保存到文件
    output_file = "../roe_ttm_data.csv"
    result_df.to_csv(output_file, index=False)
    print(f"\n数据已保存到: {output_file}")

    return result_df


if __name__ == "__main__":
    # 先测试接口
    if test_interface():
        print("\n" + "=" * 50)
        response = input("接口测试成功！是否继续批量获取数据？(y/n): ")
        if response.lower() == 'y':
            get_roe_ttm_data()
    else:
        print("\n接口测试失败，请检查配置和网络连接")