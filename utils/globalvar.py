from .ws import ConnectionManager

websocket_clients: dict[tuple[str, int], ConnectionManager] = {}

default_config = {
    # 倒计时目标：位于右侧框中的倒计时，输入日期即可，可以是中考高考期末等等，格式YYYY-MM-DD
    # 若想隐藏右侧的倒计时，请在下方冒号后填入'hidden', (包括引号)
    'countdown_target': 'hidden',

    # 星期显示：左侧框是否显示
    'week_display': True,

    # 天气预警：如果当地有天气预警，使用天气预警替代顶部横幅
    'weather_alert_override': False,
    'weather_alert_brief': False,

    # 顶部横幅：顶部横幅内容，为空则不显示横幅
    'banner_text': '',

    # 科目名称：所有课程科目的简写及其对应全称
    'subject_name': {
        '课': '配置文件损坏',
    },

    # 时间表
    'timetable': {
        'workday': {
            '00:00-23:59': 0,
        },
    },

    # 分隔线
    'divider': {
        'workday': [],
    },

    # 每日课程，长度与顺序不可更改
    'daily_class': [
        {
            'Chinese': '日',
            'English': 'SUN',
            'classList': ['课'],
            'timetable': 'workday',
        },
        {
            'Chinese': '一',
            'English': 'MON',
            'classList': ['课'],
            'timetable': 'workday',
        },
        {
            'Chinese': '二',
            'English': 'TUE',
            'classList': ['课'],
            'timetable': 'workday',
        },
        {
            'Chinese': '三',
            'English': 'WED',
            'classList': ['课'],
            'timetable': 'workday',
        },
        {
            'Chinese': '四',
            'English': 'THR',
            'classList': ['课'],
            'timetable': 'workday',
        },
        {
            'Chinese': '五',
            'English': 'FRI',
            'classList': ['课'],
            'timetable': 'workday',
        },
        {
            'Chinese': '六',
            'English': 'SAT',
            'classList': ['课'],
            'timetable': 'workday',
        },
    ],

    # 课表样式: 配置课表样式CSS变量，名称不可删改
    'css_style': {
        '--center-font-size': '30px',
        '--corner-font-size': '14px',
        '--countdown-font-size': '28px',
        '--global-border-radius': '16px',
        '--global-bg-opacity': '0.3',
        '--container-bg-padding': '8px 14px',
        '--countdown-bg-padding': '5px 12px',
        '--container-space': '16px',
        '--top-space': '16px',
        '--main-horizontal-space': '8px',
        '--divider-width': '2px',
        '--divider-margin': '6px',
        '--triangle-size': '16px',
        '--sub-font-size': '20px',
        '--banner-height': '30px',
    },
}
