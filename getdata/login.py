from iFinDPy import THS_iFinDLogin, THS_iFinDLogout

def login(username: str, password: str) -> bool:
    result = THS_iFinDLogin(username, password)
    success = (result == 0)
    print(f"登录{'成功' if success else '失败'}，返回码：{result}")
    return success

def logout():
    THS_iFinDLogout()
    print("已登出。")
