// Edge书签扩展 v2.1 - HTTP Polling + Alarm 保活
// 关键：所有监听器在顶层同步注册，alarm 保证 SW 定期唤醒

const CMD_URL = 'http://10.5.48.190:19877/cmd';
const RESULT_URL = 'http://10.5.48.190:19877/result';

// ★ 同步注册 alarm 监听（MV3 核心：必须在顶层第一轮事件循环中）
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'bm-poll') fetchCmd();
});

// ★ onInstalled: 安装/更新时触发
chrome.runtime.onInstalled.addListener(() => {
  console.log('[BM] onInstalled');
  chrome.alarms.create('bm-poll', { periodInMinutes: 0.5 }); // 30秒
  fetchCmd();
});

// ★ onStartup: 浏览器启动时触发（注意：不是 profile 启动，是浏览器启动）
chrome.runtime.onStartup.addListener(() => {
  console.log('[BM] onStartup');
  fetchCmd();
});

// ★ 顶层：确保 alarm 存在（防止 onInstalled 不触发的情况）
chrome.alarms.get('bm-poll', (alarm) => {
  if (!alarm) {
    chrome.alarms.create('bm-poll', { periodInMinutes: 0.5 });
  }
});

// ★ 顶层立即执行一次
fetchCmd();

// 轮询控制器命令
async function fetchCmd() {
  try {
    const resp = await fetch(CMD_URL);
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.action) await handleAction(data);
  } catch (e) {
    // 网络不通时静默，alarm 会重试
  }
}

// 处理书签操作
async function handleAction(data) {
  let result;
  try {
    switch (data.action) {
      case 'remove':
        result = await chrome.bookmarks.remove(data.id);
        break;
      case 'add':
        result = await chrome.bookmarks.create({ parentId: data.parentId || '1', ...data.bookmark });
        break;
      case 'update':
        result = await chrome.bookmarks.update(data.id, data.changes || {});
        break;
      case 'move':
        result = await chrome.bookmarks.move(data.id, data.destination || {});
        if (data.index !== undefined && result) {
          // index 可能没在 destination 里传，单独处理
          try { result = await chrome.bookmarks.move(data.id, { index: data.index }); } catch(e) {}
        }
        break;
      case 'tree':
        result = await chrome.bookmarks.getTree();
        break;
      case 'search':
        result = await chrome.bookmarks.search(data.query);
        break;
      case 'stats': {
        const tree = await chrome.bookmarks.getTree();
        const bar = tree[0].children?.find(c => c.id === '1');
        result = { bar_count: bar?.children?.length || 0, other_count: tree[0].children?.find(c => c.id === '2')?.children?.length || 0 };
        break;
      }
      default:
        result = { error: 'Unknown action: ' + data.action };
    }
  } catch (e) {
    result = { error: e.message };
  }
  // 返回结果
  try {
    await fetch(RESULT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cmd_id: data.cmd_id, result })
    });
  } catch (e) {}
}
