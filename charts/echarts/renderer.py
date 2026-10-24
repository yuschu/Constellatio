"""ECharts 5 Provider：服务端生成 option，浏览器端 js/echarts.js 负责 init/setOption。"""

from plugin_host.charts import ChartRenderer

DEFAULT_SERIES_TYPE = 'bar'
BAR_STACK = 'attendance'


class EChartsRenderer(ChartRenderer):
    """把容器统一的 categories/series 组装成 ECharts option（v1.6.2 支持 kind）。

    - kind='cartesian'：柱 / 线（series.type），柱默认堆叠，传 `stack=False` 可并排；
    - kind='pie'：环形饼，series=[{'name','value'}]；
    - kind='gauge'：进度环，取 series[0]['value']（0–100）；
    - compact=True：迷你图（隐藏坐标轴与留白）。
    """

    def option(self, *, categories=None, series=None, title='', kind='cartesian',
               compact=False):
        series = list(series or [])
        if kind == 'pie':
            option = self._pie(series)
        elif kind == 'gauge':
            option = self._gauge(series)
        else:
            option = self._cartesian(list(categories or []), series, compact)
        if title:
            option['title'] = {'text': title, 'left': 'center'}
        option.setdefault('aria', {'enabled': True})
        return option

    def _cartesian(self, categories, series, compact):
        items = []
        for item in series:
            data = [int(value or 0) for value in (item.get('data') or [])]
            series_type = item.get('type') or DEFAULT_SERIES_TYPE
            entry = {
                'name': item['name'],
                'type': series_type,
                'data': data,
                'emphasis': {'focus': 'series'},
            }
            if series_type == 'bar':
                stack = item.get('stack', BAR_STACK)
                if stack:
                    entry['stack'] = stack
                entry['barMaxWidth'] = 22
            else:
                entry['smooth'] = True
                entry['symbolSize'] = 4
            items.append(entry)

        if compact:
            return {
                'tooltip': {'trigger': 'axis'},
                'grid': {'left': 4, 'right': 4, 'top': 6, 'bottom': 4},
                'xAxis': {'type': 'category', 'data': categories, 'show': False},
                'yAxis': {'type': 'value', 'show': False},
                'series': items,
            }

        return {
            'tooltip': {'trigger': 'axis'},
            'legend': {'bottom': 0, 'data': [item['name'] for item in series]},
            'grid': {'left': 40, 'right': 20, 'top': 24, 'bottom': 56},
            'xAxis': {'type': 'category', 'data': categories},
            'yAxis': {'type': 'value', 'minInterval': 1},
            'series': items,
        }

    def _pie(self, series):
        data = [{
            'name': item.get('name') or item.get('label') or '',
            'value': int(item.get('value') or 0),
        } for item in series]
        return {
            'tooltip': {'trigger': 'item', 'formatter': '{b}: {c} ({d}%)'},
            'legend': {
                'bottom': 0,
                'type': 'scroll',
                'icon': 'circle',
                'itemWidth': 9,
                'itemHeight': 9,
                'itemGap': 10,
                'textStyle': {'fontSize': 11},
                'pageIconSize': 8,
                'pageTextStyle': {'fontSize': 10},
            },
            'series': [{
                'type': 'pie',
                'radius': ['38%', '60%'],
                'center': ['50%', '42%'],
                'data': data,
                'label': {'show': False},
                'emphasis': {'label': {'show': True, 'fontWeight': 'bold'}},
                'itemStyle': {'borderColor': 'transparent', 'borderWidth': 2},
            }],
        }

    def _gauge(self, series):
        first = series[0] if series else {}
        if isinstance(first, dict):
            value = first.get('value', 0)
            name = first.get('name', '')
        else:
            value, name = first, ''
        try:
            value = max(0, min(100, int(round(float(value or 0)))))
        except (TypeError, ValueError):
            value = 0
        return {
            'tooltip': {'formatter': '{b}: {c}%'},
            'series': [{
                'type': 'gauge',
                'min': 0,
                'max': 100,
                'radius': '92%',
                'center': ['50%', '50%'],
                'startAngle': 90,
                'endAngle': -270,
                'progress': {'show': True, 'width': 10, 'roundCap': True},
                'axisLine': {'lineStyle': {'width': 10}},
                'axisTick': {'show': False},
                'splitLine': {'show': False},
                'axisLabel': {'show': False},
                'pointer': {'show': False},
                'anchor': {'show': False},
                'title': {'show': False},
                'detail': {
                    'valueAnimation': True,
                    'fontSize': 18,
                    'offsetCenter': [0, '0%'],
                    'formatter': '{value}%',
                },
                'data': [{'value': value, 'name': name}],
            }],
        }
