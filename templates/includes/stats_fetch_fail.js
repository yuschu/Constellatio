{% load i18n %}{# include 是独立编译的模板，父模板的 {% load %} 不继承——缺这行两个页面直接 500 #}
// stats 图表请求的失败分支（v1.7.12）：把后端的 401 / 403 / 其它 三种口径落到界面上。
// 依赖父模板已定义 showEmpty(text)，且 showEmpty 本身不得抛错——否则会被 .catch 的
// showFallback() 覆盖成「不可用」，正好抹掉这里的区分。
function handleStatsFailure(response) {
  if (response.status === 401) {
    // 硬约束：next 只能是**页面 URL**（当前 path + query），
    // 绝不能用 el.dataset.statsUrl——那是 /plugins/…/stats/?days=7 这种接口地址，
    // 登录后会被扔到一坨 JSON 上。想「保留筛选条件」时极易犯这个错。
    window.location.assign('{% url "auth:login" %}?next=' +
      encodeURIComponent(window.location.pathname + window.location.search));
    return true;
  }
  if (response.status === 403) {
    showEmpty('{% trans "无权查看该数据" %}');
    return true;
  }
  showEmpty('{% trans "数据暂时不可用" %}');
  return true;
}
