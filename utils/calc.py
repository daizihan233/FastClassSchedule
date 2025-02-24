import datetime


def from_str_to_date(date_str: str, format_str: str = '%Y-%m-%d') -> datetime.date:
    """
    将一个字符串转换为日期对象
    :param date_str: 日期，如 2025-03-14
    :param format_str: 字符串格式，默认为 '%Y-%m-%d'，如 '2025-03-14'
    :return: 一个日期对象
    """
    return datetime.datetime.strptime(date_str, format_str).date()

def weeks(start_date: datetime.date, end_date: datetime.date = datetime.date.today()) -> int:
    """
    计算从 start_date 到当前日期的周数
    :param start_date: 起始日期
    :param end_date: 结束日期，默认为今天
    :return: 周数（按自然周计算，也就是即使开始日期是周日，结束日期是下周一，也会计算为第 2 周）
    """
    return (
        (
            (end_date + datetime.timedelta(days=7 - end_date.isoweekday())) -
            (start_date - datetime.timedelta(days=start_date.isoweekday()))
        ).days
    ) // 7
