const API = '/api';
const state = {
  token: localStorage.getItem('nexus_token') || '',
  user: JSON.parse(localStorage.getItem('nexus_user') || 'null'),
  view: 'overview',
  authMode: 'login',
  articles: [],
  tickets: [],
  agents: [],
  answer: null,
  ticketFilter: 'all',
  libraryCategory: '',
  libraryDifficulty: '',
  expandedTicket: null,
};
const categories = ['Hardware', 'Software', 'Network', 'Database', 'Cloud', 'Security', 'Programming'];
const categoryIcons = {Hardware:'◉',Software:'▣',Network:'⌁',Database:'▥',Cloud:'☁',Security:'⬡',Programming:'⌘'};
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function esc(value = '') {
  return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function authHeaders(json = true) {
  const headers = {};
  if (json) headers['Content-Type'] = 'application/json';
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  return headers;
}
async function api(path, options = {}) {
  const headers = {...authHeaders(!(options.body instanceof FormData)), ...(options.headers || {})};
  const response = await fetch(`${API}${path}`, {...options, headers});
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && state.token) signOut(false);
    throw new Error(data.detail || 'Something went wrong. Please try again.');
  }
  return data;
}
function toast(message, error = false) {
  const node = document.createElement('div');
  node.className = `toast${error ? ' error' : ''}`;
  node.textContent = message;
  $('#toastRegion').append(node);
  setTimeout(() => node.remove(), 3600);
}
function setError(selector, message) {
  const node = $(selector);
  node.textContent = message;
  node.classList.toggle('hidden', !message);
}
function setAuth(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem('nexus_token', token);
  localStorage.setItem('nexus_user', JSON.stringify(user));
  updateIdentity();
}
function signOut(showToast = true) {
  state.token = '';
  state.user = null;
  localStorage.removeItem('nexus_token');
  localStorage.removeItem('nexus_user');
  updateIdentity();
  refreshDashboard();
  if (showToast) toast('You have signed out.');
}
function updateIdentity() {
  const user = state.user;
  $('#profileName').textContent = user?.name || 'Guest session';
  $('#profileRole').textContent = user ? (user.role === 'user' ? 'Member account' : `${user.role[0].toUpperCase()}${user.role.slice(1)} access`) : 'Sign in to sync work';
  $('#userAvatar').textContent = user ? user.name.split(/\s+/).map(part => part[0]).slice(0,2).join('').toUpperCase() : '?';
  $('#authButton').innerHTML = user ? 'Sign out <span>↗</span>' : 'Sign in <span>↗</span>';
  $('#adminNav').classList.toggle('hidden', !user || !['admin','agent'].includes(user.role));
  if (user) $('#adminNav span:nth-of-type(2)').textContent = user.role === 'agent' ? 'Agent workspace' : 'Admin console';
  $('#knowledgeStaffControls').classList.toggle('hidden', !user || !['admin','agent'].includes(user.role));
  $('#footerApiStatus').textContent = $('#footerApiStatus').dataset.ai === 'true' ? 'AI ANSWERS ENABLED' : 'LOCAL KNOWLEDGE MODE';
  if (state.view === 'admin' && !['admin','agent'].includes(user?.role)) showView('overview');
}
function showView(name) {
  if (name === 'admin' && !['admin','agent'].includes(state.user?.role)) {
    openAuth();
    return;
  }
  state.view = name;
  $$('.view-panel').forEach(panel => panel.classList.add('hidden'));
  $(`#${name}View`)?.classList.remove('hidden');
  $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === name));
  const names = {overview:'Overview',knowledge:'Knowledge base',tickets:'Support tickets',bookmarks:'Saved solutions',admin:'Admin console'};
  $('#crumbCurrent').textContent = names[name] || 'Overview';
  $('#sidebar').classList.remove('open');
  $('#sidebarScrim').classList.add('hidden');
  if (name === 'knowledge') loadArticles();
  if (name === 'tickets') loadTickets();
  if (name === 'bookmarks') loadBookmarks();
  if (name === 'admin') loadAdmin();
  window.scrollTo({top:0,behavior:'smooth'});
}
function openAuth(mode = 'login') {
  setAuthMode(mode);
  $('#authDialog').showModal();
}
function setAuthMode(mode) {
  state.authMode = mode;
  const register = mode === 'register';
  $('#authTitle').innerHTML = register ? 'Create your account<span>.</span>' : 'Welcome back<span>.</span>';
  $('#authSubtitle').textContent = register ? 'Your support history, all in one place.' : 'Sign in to sync your searches and tickets.';
  $('#nameField').classList.toggle('hidden', !register);
  $('#nameField input').required = register;
  $('#authForm [name="password"]').autocomplete = register ? 'new-password' : 'current-password';
  $('#authSubmit').innerHTML = register ? 'Create account <span>↗</span>' : 'Sign in <span>↗</span>';
  $$('.auth-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.authMode === mode));
  setError('#authError','');
}
function renderCategories() {
  const options = categories.map(category => `<option value="${esc(category)}">${esc(category)}</option>`).join('');
  $('#categoryFilter').insertAdjacentHTML('beforeend', options);
  $('#libraryCategory').insertAdjacentHTML('beforeend', options);
  $('#articleCategory').innerHTML = options;
  $('#categoryGrid').innerHTML = categories.map((category, index) => `<button class="category-tile" data-category="${esc(category)}"><span class="category-symbol" style="color:${['#de785e','#397c68','#648eb4','#c1984b','#688e84','#ae6b57','#517e77'][index]}">${categoryIcons[category]}</span><span class="category-name">${esc(category)}</span><span class="category-total">Browse articles ↗</span></button>`).join('');
  $('#libraryCategoryList').innerHTML = categories.map(category => `<button class="rail-filter" data-library-category="${esc(category)}">${esc(category)}</button>`).join('');
}
function localHistory() {
  try { return JSON.parse(localStorage.getItem('nexus_recent') || '[]'); } catch { return []; }
}
function saveHistory(query) {
  const history = [query, ...localHistory().filter(item => item !== query)].slice(0,5);
  localStorage.setItem('nexus_recent', JSON.stringify(history));
}
function renderRecent(searches = []) {
  const personal = searches.length ? searches.map(item => item.query) : localHistory();
  $('#recentSearches').innerHTML = personal.length ? personal.slice(0,5).map((query,index) => `<div class="recent-row"><span class="recent-symbol">⌕</span><button class="recent-query" data-query="${esc(query)}">${esc(query)}</button><span class="row-time">${index === 0 ? 'LATEST' : 'RECENT'}</span></div>`).join('') : '<div class="empty-line">Your recent searches will appear here.</div>';
}
function renderPopular(items = []) {
  $('#popularProblems').innerHTML = items.length ? items.map((item,index) => `<div class="popular-row"><span class="popular-rank">0${index+1}</span><button class="popular-name" data-query="${esc(item.query)}">${esc(item.query)}</button><span class="popular-count">${item.count} searches</span></div>`).join('') : '<div class="empty-line">Community searches, updated as people ask.</div>';
}
function ticketStatusClass(status) { return status.toLowerCase().replace(/\s+/g,'-'); }
function renderPreviewTickets(tickets = []) {
  $('#ticketNavCount').textContent = tickets.filter(ticket => ['Open','In Progress'].includes(ticket.status)).length;
  $('#ticketPreview').innerHTML = tickets.length ? tickets.slice(0,4).map(ticket => `<div class="mini-ticket"><span class="ticket-dot"></span><span class="ticket-subject">${esc(ticket.subject)}</span><span class="status-pill ${ticketStatusClass(ticket.status)}">${esc(ticket.status)}</span></div>`).join('') : `<div class="empty-line">${state.user ? 'No tickets in your queue.' : 'Sign in to see your support queue.'}</div>`;
}
async function refreshDashboard() {
  if (!state.token) {
    renderRecent();
    renderPreviewTickets([]);
    $('#popularProblems').innerHTML = '<div class="empty-line">Searches from your team will appear here.</div>';
    return;
  }
  try {
    const data = await api('/dashboard');
    state.user = data.user;
    localStorage.setItem('nexus_user', JSON.stringify(data.user));
    updateIdentity();
    renderRecent(data.recent_searches);
    renderPopular(data.popular);
    renderPreviewTickets(data.tickets);
    $('#ticketNavCount').textContent = data.stats.open_tickets;
    if (data.categories?.length) updateCategoryOptions(data.categories);
  } catch (error) { if (state.token) toast(error.message,true); }
}
function updateCategoryOptions(values) {
  [$('#categoryFilter'),$('#libraryCategory')].forEach(select => {
    const first = select.options[0].outerHTML;
    const selected = select.value;
    select.innerHTML = first + values.map(value => `<option value="${esc(value)}">${esc(value)}</option>`).join('');
    select.value = selected;
  });
}
async function runSearch(query = $('#searchInput').value) {
  query = query.trim();
  if (query.length < 3) { toast('Enter a little more detail to search.'); $('#searchInput').focus(); return; }
  $('#searchInput').value = query;
  $('#suggestions').classList.add('hidden');
  $('#overviewGrid').classList.add('hidden');
  $('#overviewSecondGrid').classList.add('hidden');
  $('#answerPanel').classList.remove('hidden');
  $('#answerTitle').textContent = 'Searching the knowledge base...';
  $('#answerText').textContent = 'Matching your question to documented solutions.';
  $('#sourceList').innerHTML = '';
  $('#sourceCount').textContent = '';
  $('#answerConfidence').textContent = '';
  $('#detectedErrors').classList.add('hidden');
  $('#answerDisclaimer').textContent = 'Answers are based on the sources shown above.';
  const params = new URLSearchParams();
  const filters = {category:'categoryFilter',technology:'technologyFilter',product:'productFilter',error_code:'errorFilter',difficulty:'difficultyFilter',tag:'tagFilter'};
  Object.entries(filters).forEach(([key,id]) => { const value = $(`#${id}`).value.trim(); if (value) params.set(key,value); });
  const date = $('#dateFilter').value;
  if (date) params.set('date_after',date);
  try {
    const data = await api(`/search?${params}`, {method:'POST',body:JSON.stringify({query})});
    state.answer = data;
    saveHistory(query);
    $('#answerTitle').textContent = data.results.length ? 'Here’s what we found' : 'No reliable match yet';
    $('#answerText').textContent = data.answer;
    $('#answerConfidence').textContent = data.confidence ? ` · ${(data.confidence*100).toFixed(0)}% match` : '';
    $('#sourceCount').textContent = `${data.results.length} ${data.results.length === 1 ? 'source' : 'sources'}`;
    $('#sourceList').innerHTML = data.results.length ? data.results.map(article => `<article class="source-card"><span class="source-type">${esc(article.category.slice(0,3).toUpperCase())}</span><div class="source-info"><strong>${esc(article.title)}</strong><small>${esc(article.category)}${article.technology ? ` · ${esc(article.technology)}` : ''}</small></div><span class="source-score">${Math.round(article.score*100)}%</span><button class="tiny-action save-source" data-id="${article.id}" title="Save solution">☆</button></article>`).join('') : '<div class="empty-line">Try a product name, error code, or different wording. You can also open a support ticket.</div>';
    const errorNodes = data.detected_errors || [];
    if (errorNodes.length) { $('#detectedErrors').innerHTML = `<span>Detected</span> ${errorNodes.map(value => `<span>${esc(value)}</span>`).join('')}`; $('#detectedErrors').classList.remove('hidden'); }
    $('#answerDisclaimer').textContent = data.ai_generated ? 'AI answer generated from the listed knowledge sources.' : 'Knowledge-base answer. Configure Gemini or Groq to enable generated responses.';
    $('#overviewGrid').classList.remove('hidden');
    $('#overviewSecondGrid').classList.remove('hidden');
    refreshDashboard();
  } catch (error) {
    $('#answerTitle').textContent = 'Search could not be completed';
    $('#answerText').textContent = error.message;
    toast(error.message,true);
  }
}
function renderArticles(articles, target = '#articleList') {
  const node = $(target);
  if (!articles.length) { node.innerHTML = '<div class="empty-state"><span>▤</span><strong>No matching articles yet.</strong><p>Try another keyword or clear the current filters.</p></div>'; return; }
  node.innerHTML = articles.map(article => `<article class="article-card"><div class="article-card-top"><span class="article-category">${esc(article.category)}${article.technology ? ` / ${esc(article.technology)}` : ''}</span><span class="article-level">${esc(article.difficulty || 'Beginner')}</span></div><h3>${esc(article.title)}</h3><p>${esc(article.summary || article.content.slice(0,180))}</p><div class="article-card-bottom"><div class="tag-list">${(article.tags || '').split(',').filter(Boolean).slice(0,4).map(tag => `<span class="tag-chip">${esc(tag.trim())}</span>`).join('')} ${article.error_code ? `<span class="tag-chip">${esc(article.error_code)}</span>` : ''}</div><div class="article-card-actions"><button class="tiny-action use-article" data-id="${article.id}">View solution ↗</button><button class="tiny-action save-source" data-id="${article.id}" title="Save solution">☆</button></div></div></article>`).join('');
}
async function loadArticles() {
  try {
    const params = new URLSearchParams();
    if ($('#librarySearch').value.trim()) params.set('q',$('#librarySearch').value.trim());
    if (state.libraryCategory) params.set('category',state.libraryCategory);
    const {articles} = await api(`/articles?${params}`);
    state.articles = articles;
    const filtered = articles.filter(article => !state.libraryDifficulty || article.difficulty === state.libraryDifficulty);
    renderArticles(filtered);
    $('#libraryCount').textContent = `${filtered.length} ARTICLES`;
    $('#allArticleCount').textContent = articles.length;
    $$('.rail-filter[data-library-category]').forEach(item => item.classList.toggle('active', item.dataset.libraryCategory === state.libraryCategory));
  } catch (error) { toast(error.message,true); }
}
async function loadTickets() {
  if (!state.token) {
    $('#ticketList').innerHTML = '<div class="empty-state"><span>◷</span><strong>Sign in to see your support queue.</strong><p>Track progress, add context, and follow up with your support team.</p><button class="primary-button" id="ticketSignIn">Sign in to continue</button></div>';
    return;
  }
  try {
    const {tickets} = await api('/tickets');
    state.tickets = tickets;
    state.agents = ['agent','admin'].includes(state.user?.role) ? (await api('/agents')).agents : [];
    renderTickets();
    renderPreviewTickets(tickets);
  }
  catch (error) { toast(error.message,true); }
}
function renderTickets() {
  const filtered = state.ticketFilter === 'all' ? state.tickets : state.tickets.filter(ticket => ticket.status === state.ticketFilter);
  if (!filtered.length) { $('#ticketList').innerHTML = '<div class="empty-state"><span>◷</span><strong>No tickets in this view.</strong><p>When something needs a closer look, start a support request.</p></div>'; return; }
  const isStaff = ['agent','admin'].includes(state.user?.role);
  $('#ticketList').innerHTML = filtered.map(ticket => {
    const statusControl = isStaff ? `<select name="status" aria-label="Ticket status"><option${ticket.status==='Open'?' selected':''}>Open</option><option${ticket.status==='In Progress'?' selected':''}>In Progress</option><option${ticket.status==='Resolved'?' selected':''}>Resolved</option><option${ticket.status==='Closed'?' selected':''}>Closed</option></select>` : '';
    const assigneeControl = isStaff ? `<select name="assignee_id" aria-label="Assign support agent"><option value="">Unassigned</option>${state.agents.map(agent => `<option value="${agent.id}"${ticket.assignee_id===agent.id?' selected':''}>${esc(agent.name)}</option>`).join('')}</select>` : '';
    const comments = (ticket.comments || []).map(comment => `<div class="ticket-comment">${esc(comment.content)}<small>${esc(comment.author)} · ${new Date(comment.created_at).toLocaleString()}</small></div>`).join('');
    const detail = state.expandedTicket === ticket.id ? `<div class="ticket-card-detail"><p>${esc(ticket.description)}</p><div class="ticket-comments" id="comments-${ticket.id}">${comments}</div><form class="ticket-update-form" data-ticket-update="${ticket.id}">${statusControl}${assigneeControl}<input name="comment" placeholder="Add a comment or update..."><button class="tiny-action" type="submit">Send update ↗</button>${isStaff && ticket.status === 'Resolved' ? `<button class="tiny-action convert-ticket" type="button" data-ticket-id="${ticket.id}">Add to knowledge</button>` : ''}</form></div>` : '';
    return `<article class="ticket-card"><div class="ticket-card-summary" data-expand-ticket="${ticket.id}"><span class="ticket-key">${esc(ticket.ticket_key)}</span><div class="ticket-summary-copy"><strong>${esc(ticket.subject)}</strong><small>Opened ${new Date(ticket.created_at).toLocaleDateString()}${ticket.assignee_id ? ' · Assigned to support' : ''}</small></div><span class="status-pill ${ticketStatusClass(ticket.status)}">${esc(ticket.status)}</span><span class="ticket-priority ${esc(ticket.priority.toLowerCase())}">${esc(ticket.priority)}</span><span>⌄</span></div>${detail}</article>`;
  }).join('');
}
async function loadBookmarks() {
  if (!state.token) { $('#bookmarkList').innerHTML = '<div class="empty-state"><span>☆</span><strong>Sign in to save solutions.</strong><p>Your bookmarked fixes are available on any signed-in session.</p><button class="primary-button" id="bookmarkSignIn">Sign in</button></div>'; return; }
  try { const {articles} = await api('/bookmarks'); renderArticles(articles,'#bookmarkList'); }
  catch (error) { toast(error.message,true); }
}
async function loadAdmin() {
  try {
    const agentMode = state.user.role === 'agent';
    const stats = await api(agentMode ? '/agent/stats' : '/admin/stats');
    $('#peopleSection').classList.toggle('hidden',agentMode);
    const metrics = agentMode ? [['Assigned tickets',stats.assigned],['In progress',stats.in_progress],['Knowledge articles',stats.articles]] : [['People',stats.users],['Knowledge articles',stats.articles],['Unresolved',stats.unresolved.length]];
    $('#adminMetrics').innerHTML = metrics.map(([label,value]) => `<div class="metric-card"><span class="metric-label">${label.toUpperCase()}</span><strong class="metric-value">${value}</strong></div>`).join('');
    $('#adminFrequent').innerHTML = stats.frequent.length ? stats.frequent.map((item,index) => `<div class="popular-row"><span class="popular-rank">0${index+1}</span><span class="popular-name">${esc(item.query)}</span><span class="popular-count">${item.count}</span></div>`).join('') : '<div class="empty-line">Search trends will appear as your team uses the system.</div>';
    $('#adminUnresolved').innerHTML = stats.unresolved.length ? stats.unresolved.map(ticket => `<div class="mini-ticket"><span class="ticket-dot"></span><span class="ticket-subject">${esc(ticket.subject)}</span><span class="status-pill ${ticketStatusClass(ticket.status)}">${esc(ticket.status)}</span></div>`).join('') : '<div class="empty-line">No unresolved tickets.</div>';
    if (!agentMode) {
      const {users} = await api('/admin/users');
      $('#userTableBody').innerHTML = users.map(user => `<tr><td>${esc(user.name)}<br><span style="color:#929b95">${esc(user.email)}</span></td><td><select data-role-user="${user.id}"${user.id===state.user.id?' disabled':''}><option value="user"${user.role==='user'?' selected':''}>User</option><option value="agent"${user.role==='agent'?' selected':''}>Agent</option><option value="admin"${user.role==='admin'?' selected':''}>Admin</option></select></td><td>${new Date(user.created_at).toLocaleDateString()}</td><td>${user.id===state.user.id?'YOU':''}</td></tr>`).join('');
    }
  } catch (error) { toast(error.message,true); showView('overview'); }
}
async function showArticleSolution(id) {
  const article = state.articles.find(item => item.id === Number(id));
  if (!article) return;
  showView('overview');
  $('#searchInput').value = article.title;
  $('#answerPanel').classList.remove('hidden');
  $('#overviewGrid').classList.remove('hidden');
  $('#overviewSecondGrid').classList.remove('hidden');
  state.answer = {results:[article]};
  $('#answerTitle').textContent = article.title;
  $('#answerText').textContent = `${article.summary || ''}${article.summary ? '\n\n' : ''}${article.content}`;
  $('#answerConfidence').textContent = '';
  $('#sourceCount').textContent = '1 source';
  $('#sourceList').innerHTML = `<article class="source-card"><span class="source-type">${esc(article.category.slice(0,3).toUpperCase())}</span><div class="source-info"><strong>${esc(article.title)}</strong><small>${esc(article.category)}${article.technology ? ` · ${esc(article.technology)}` : ''}</small></div><button class="tiny-action save-source" data-id="${article.id}">☆</button></article>`;
  $('#answerDisclaimer').textContent = 'Full solution from the selected knowledge article.';
  window.scrollTo({top:240,behavior:'smooth'});
}
async function saveArticle(id) {
  if (!state.token) { openAuth(); return; }
  try { await api(`/bookmarks/${id}`,{method:'POST'}); toast('Solution saved to your library.'); }
  catch (error) { toast(error.message,true); }
}
function openTicketDialog(prefill = '') {
  if (!state.token) { openAuth('login'); toast('Sign in first to open a support ticket.'); return; }
  if (prefill) { $('#ticketForm [name="subject"]').value = prefill.slice(0,240); $('#ticketForm [name="description"]').value = state.answer?.answer || prefill; }
  $('#ticketDialog').showModal();
}

$('#todayDate').textContent = new Intl.DateTimeFormat('en',{weekday:'short',month:'short',day:'2-digit'}).format(new Date()).toUpperCase();
renderCategories();
updateIdentity();
if (localStorage.getItem('nexus_theme') === 'dark') document.documentElement.classList.add('theme-dark');
$('#footerApiStatus').dataset.ai = 'false';
api('/health').then(data => { $('#footerApiStatus').dataset.ai = String(data.ai_enabled); updateIdentity(); }).catch(() => {});
refreshDashboard();

$$('.nav-item').forEach(item => item.addEventListener('click', () => showView(item.dataset.view)));
$$('[data-go-view]').forEach(item => item.addEventListener('click', () => showView(item.dataset.goView)));
$('#profileButton').addEventListener('click', () => state.user ? signOut() : openAuth());
$('#authButton').addEventListener('click', () => state.user ? signOut() : openAuth());
$('#themeToggle').addEventListener('click', () => {
  document.documentElement.classList.toggle('theme-dark');
  localStorage.setItem('nexus_theme',document.documentElement.classList.contains('theme-dark')?'dark':'light');
});
$('#mobileMenu').addEventListener('click', () => { $('#sidebar').classList.add('open'); $('#sidebarScrim').classList.remove('hidden'); });
$('#sidebarScrim').addEventListener('click', () => { $('#sidebar').classList.remove('open'); $('#sidebarScrim').classList.add('hidden'); });
$('#filterToggle').addEventListener('click', () => $('#filterRow').classList.toggle('hidden'));
$('#clearSearch').addEventListener('click', () => { $('#searchInput').value=''; $('#clearSearch').classList.add('hidden'); $('#searchInput').focus(); });
$('#searchInput').addEventListener('input', async event => {
  const query = event.target.value.trim();
  $('#clearSearch').classList.toggle('hidden',!query);
  if (query.length < 2) { $('#suggestions').classList.add('hidden'); return; }
  try {
    const {suggestions} = await api(`/search/suggestions?q=${encodeURIComponent(query)}`);
    if (document.activeElement === event.target && suggestions.length) {
      $('#suggestions').innerHTML = suggestions.map(text => `<button type="button" data-suggestion="${esc(text)}">⌕ &nbsp; ${esc(text)}</button>`).join('');
      $('#suggestions').classList.remove('hidden');
    }
  } catch { /* Suggestions are optional while the API is warming up. */ }
});
$('#searchInput').addEventListener('blur', () => setTimeout(() => $('#suggestions').classList.add('hidden'),130));
$('#suggestions').addEventListener('mousedown', event => {
  const button = event.target.closest('[data-suggestion]');
  if (button) { event.preventDefault(); $('#searchInput').value = button.dataset.suggestion; $('#suggestions').classList.add('hidden'); runSearch(button.dataset.suggestion); }
});
$('#searchForm').addEventListener('submit', event => { event.preventDefault(); runSearch(); });
$('#searchForm').addEventListener('keydown', event => { if (event.key === 'Enter' && event.target.matches('input')) { event.preventDefault(); runSearch(); } });
document.addEventListener('click', event => {
  const queryButton = event.target.closest('[data-query]');
  if (queryButton) { showView('overview'); runSearch(queryButton.dataset.query); }
  const category = event.target.closest('[data-category]');
  if (category) { state.libraryCategory = category.dataset.category; $('#libraryCategory').value = state.libraryCategory; showView('knowledge'); }
  const useButton = event.target.closest('.use-article');
  if (useButton) showArticleSolution(useButton.dataset.id);
  const saveButton = event.target.closest('.save-source');
  if (saveButton) saveArticle(saveButton.dataset.id);
  const expandButton = event.target.closest('[data-expand-ticket]');
  if (expandButton) {
    const id = Number(expandButton.dataset.expandTicket);
    if (state.expandedTicket === id) { state.expandedTicket = null; renderTickets(); }
    else { state.expandedTicket = id; api(`/tickets/${id}`).then(ticket => { state.tickets = state.tickets.map(item => item.id === id ? ticket : item); renderTickets(); }).catch(error => toast(error.message,true)); }
  }
  const conversion = event.target.closest('.convert-ticket');
  if (conversion) api(`/tickets/${conversion.dataset.ticketId}/knowledge`,{method:'POST'}).then(() => toast('Resolved case added to the knowledge base.')).catch(error => toast(error.message,true));
  if (event.target.id === 'ticketSignIn' || event.target.id === 'bookmarkSignIn') openAuth();
});
$('#viewHistory').addEventListener('click', () => {
  const history = localHistory();
  if (!history.length) { toast(state.user ? 'Your search history will appear here as you search.' : 'Sign in to sync search history.'); return; }
  toast(`Recent: ${history.slice(0,3).join(' · ')}`);
});
$$('.prompt-chip').forEach(button => button.addEventListener('click', () => runSearch(button.dataset.query)));
$('#closeAnswer').addEventListener('click', () => { $('#answerPanel').classList.add('hidden'); $('#overviewGrid').classList.remove('hidden'); $('#overviewSecondGrid').classList.remove('hidden'); });
$('#createFromAnswer').addEventListener('click', () => openTicketDialog(state.answer?.query || $('#searchInput').value));
$('#helpfulButton').addEventListener('click', () => sendFeedback(true));
$('#notHelpfulButton').addEventListener('click', () => sendFeedback(false));
async function sendFeedback(helpful) {
  const articleId = state.answer?.results?.[0]?.id;
  if (!articleId) { toast('There is no source article to rate.'); return; }
  if (!state.token) { openAuth(); return; }
  try { await api('/feedback',{method:'POST',body:JSON.stringify({article_id:articleId,helpful})}); $$('.feedback-button').forEach(button => button.classList.remove('selected')); (helpful?$('#helpfulButton'):$('#notHelpfulButton')).classList.add('selected'); toast('Thanks for helping improve these answers.'); }
  catch (error) { toast(error.message,true); }
}
$$('.auth-tab').forEach(button => button.addEventListener('click', () => setAuthMode(button.dataset.authMode)));
$('#authForm').addEventListener('submit', async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  const endpoint = state.authMode === 'register' ? '/auth/register' : '/auth/login';
  try { const data = await api(endpoint,{method:'POST',body:JSON.stringify(values)}); setAuth(data.access_token,data.user); $('#authDialog').close(); event.currentTarget.reset(); toast(`Welcome${data.user.name ? `, ${data.user.name.split(' ')[0]}` : ''}.`); refreshDashboard(); if (state.view === 'tickets') loadTickets(); }
  catch (error) { setError('#authError',error.message); }
});
$('#newTicketButton').addEventListener('click', () => openTicketDialog());
$('#ticketForm').addEventListener('submit', async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  try { const ticket = await api('/tickets',{method:'POST',body:JSON.stringify(values)}); $('#ticketDialog').close(); event.currentTarget.reset(); toast(`Ticket ${ticket.ticket_key} created.`); showView('tickets'); loadTickets(); refreshDashboard(); }
  catch (error) { setError('#ticketError',error.message); }
});
$$('[data-ticket-filter]').forEach(button => button.addEventListener('click', () => { state.ticketFilter=button.dataset.ticketFilter; $$('.ticket-filter').forEach(item => item.classList.toggle('active',item===button)); renderTickets(); }));
$('#ticketList').addEventListener('submit', async event => {
  const form = event.target.closest('[data-ticket-update]');
  if (!form) return;
  event.preventDefault();
  const values = Object.fromEntries(new FormData(form));
  const payload = {};
  if (values.status) payload.status = values.status;
  if (Object.hasOwn(values,'assignee_id')) payload.assignee_id = values.assignee_id ? Number(values.assignee_id) : null;
  if (values.comment?.trim()) payload.comment = values.comment.trim();
  try { const ticket = await api(`/tickets/${form.dataset.ticketUpdate}`,{method:'PATCH',body:JSON.stringify(payload)}); state.tickets=state.tickets.map(item=>item.id===ticket.id?ticket:item); renderTickets(); toast('Ticket updated.'); }
  catch (error) { toast(error.message,true); }
});
$('#librarySearch').addEventListener('input', debounce(loadArticles,250));
$('#libraryCategory').addEventListener('change', () => { state.libraryCategory=$('#libraryCategory').value; loadArticles(); });
document.addEventListener('click', event => {
  const category = event.target.closest('[data-library-category]');
  if (category) { state.libraryCategory=category.dataset.libraryCategory; $('#libraryCategory').value=state.libraryCategory; loadArticles(); }
  const difficulty = event.target.closest('[data-difficulty]');
  if (difficulty) { state.libraryDifficulty=state.libraryDifficulty===difficulty.dataset.difficulty?'':difficulty.dataset.difficulty; loadArticles(); }
});
$('#newArticleButton').addEventListener('click', () => $('#articleDialog').showModal());
$('#articleForm').addEventListener('submit', async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  try { await api('/articles',{method:'POST',body:JSON.stringify(values)}); $('#articleDialog').close(); event.currentTarget.reset(); toast('Article published to the knowledge base.'); loadArticles(); }
  catch (error) { setError('#articleError',error.message); }
});
$('#uploadButton').addEventListener('click', () => $('#documentInput').click());
$('#documentInput').addEventListener('change', async event => {
  const file=event.target.files[0]; if (!file) return;
  const form=new FormData(); form.append('file',file); form.append('category',$('#libraryCategory').value||'Software');
  try { await api('/articles/upload',{method:'POST',body:form}); toast('Document processed and added to the knowledge base.'); loadArticles(); }
  catch (error) { toast(error.message,true); }
  event.target.value='';
});
$('#adminView').addEventListener('change', async event => {
  const select=event.target.closest('[data-role-user]');
  if (!select) return;
  try { await api(`/admin/users/${select.dataset.roleUser}/role`,{method:'PATCH',body:JSON.stringify({role:select.value})}); toast('Access role updated.'); }
  catch (error) { toast(error.message,true); loadAdmin(); }
});
$('#authDialog').addEventListener('click', event => { if (event.target === event.currentTarget) event.currentTarget.close(); });
$('#ticketDialog').addEventListener('click', event => { if (event.target === event.currentTarget) event.currentTarget.close(); });
$('#articleDialog').addEventListener('click', event => { if (event.target === event.currentTarget) event.currentTarget.close(); });
function debounce(fn, delay) { let timer; return (...args) => { clearTimeout(timer); timer=setTimeout(()=>fn(...args),delay); }; }
