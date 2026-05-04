const els = {
  dataAtualizacao: document.getElementById('dataAtualizacao'),
  globalPercent: document.getElementById('globalPercent'),
  ringProgress: document.getElementById('ringProgress'),
  motivationalTag: document.getElementById('motivationalTag'),
  totalCenarios: document.getElementById('totalCenarios'),
  totalConcluidos: document.getElementById('totalConcluidos'),
  totalEmAndamento: document.getElementById('totalEmAndamento'),
  totalNaoIniciado: document.getElementById('totalNaoIniciado'),
  totalBloqueados: document.getElementById('totalBloqueados'),
  totalCancelados: document.getElementById('totalCancelados'),
  headlineCallout: document.getElementById('headlineCallout'),
  headlinePill: document.getElementById('headlinePill'),
  leaderboard: document.getElementById('leaderboard'),
  statusBars: document.getElementById('statusBars'),
  areaBoard: document.getElementById('areaBoard'),
  focusTable: document.getElementById('focusTable')
};

const RING_CIRCUMFERENCE = 301.59;
const AUTO_CSV_NAME = 'output/Cenarios_Consolidados_atualizado.csv';
const AUTO_REFRESH_INTERVAL_MS = 180000; // 3 minutos

const motivationalMessages = [
  { threshold: 0, tag: 'Aquecendo os motores', title: 'O jogo começou. Agora é sair do planejamento e entrar na execução.', pill: 'Sem moleza' },
  { threshold: 20, tag: 'Ritmo ganhando corpo', title: 'Tem avanço na pista. Agora é apertar o passo e reduzir o estoque de cenário parado.', pill: 'Subindo de nível' },
  { threshold: 40, tag: 'Competição de verdade', title: 'O time já mostrou serviço. Quem acelerar agora começa a cheirar pódio.', pill: 'Olho no ranking' },
  { threshold: 60, tag: 'Sprint valendo respeito', title: 'A reta ficou bonita. A turma que concluir agora vira referência, não desculpa.', pill: 'Fase quente' },
  { threshold: 80, tag: 'Cheiro de vitória', title: 'A meta está no radar. Faltam poucos golpes certeiros para transformar esforço em resultado.', pill: 'Pódio à vista' },
  { threshold: 100, tag: 'Missão cumprida', title: 'Todos os cenários concluídos. Aqui não teve conversa: teve entrega.', pill: 'Lenda desbloqueada' }
];

document.addEventListener('DOMContentLoaded', () => {
  tryAutoLoadCsv();

  setInterval(() => {
    tryAutoLoadCsv();
  }, AUTO_REFRESH_INTERVAL_MS);
});

async function tryAutoLoadCsv() {
  const candidates = [
    AUTO_CSV_NAME,
    `./${AUTO_CSV_NAME}`,
    '/output/Cenarios_Consolidados_atualizado.csv'
  ];

  setGeneratedAt(`Lendo ${AUTO_CSV_NAME}...`);

  for (const candidate of candidates) {
    try {
      const response = await fetch(`${candidate}?t=${Date.now()}`, {
        cache: 'no-store'
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const buffer = await response.arrayBuffer();
      const text = new TextDecoder('utf-8').decode(buffer);
      parseCsvText(text);
      return;
    } catch (error) {
      console.warn(`Falha ao carregar CSV em ${candidate}:`, error);
    }
  }

  setGeneratedAt(`Arquivo processado não encontrado. Verifique a pasta output e o nome ${AUTO_CSV_NAME}.`);
}

function parseCsvText(text) {
  const parsed = Papa.parse(text, {
    header: true,
    skipEmptyLines: true,
    delimiter: ';'
  });

  const rows = parsed.data || [];
  renderDashboard(rows);
  updateGeneratedAt(rows);
}

function updateGeneratedAt(rows) {
  if (!els.dataAtualizacao) return;

  if (!rows.length) {
    setGeneratedAt('CSV sem dados para exibir.');
    return;
  }

  const generatedAt = getValue(rows[0], 'Gerado em');
  if (generatedAt) {
    setGeneratedAt(generatedAt);
  } else {
    setGeneratedAt("Coluna 'Gerado em' não encontrada no CSV processado.");
  }
}

function setGeneratedAt(message) {
  if (els.dataAtualizacao) {
    els.dataAtualizacao.textContent = message;
  }
}

function normalize(text = '') {
  return String(text)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

function findKey(row, target) {
  const entries = Object.keys(row).map(key => [key, normalize(key)]);
  const hit = entries.find(([, norm]) => norm === normalize(target));
  return hit ? hit[0] : null;
}

function getValue(row, target, fallback = '') {
  const key = findKey(row, target);
  return key ? row[key] : fallback;
}

function renderDashboard(rows) {
  const cleanRows = rows
    .filter(row => Object.values(row).some(v => String(v).trim() !== ''))
    .map(row => ({
      identificador: getValue(row, 'Identificador'),
      cenario: getValue(row, 'Cenário') || getValue(row, 'Cenario'),
      area: getValue(row, 'Área de Negócio') || getValue(row, 'Area de Negocio') || 'Não informada',
      lider: getValue(row, 'Lider do Cenário') || getValue(row, 'Líder do Cenário') || 'Sem líder',
      statusOriginal: getValue(row, 'Status') || 'Sem status',
      prioridade: getValue(row, 'Grupo de Prioridade'),
      execucoes: Number(String(getValue(row, 'Qtde. Execuções Concluídas') || '0').replace(',', '.')) || 0
    }));

  const total = cleanRows.length;
  const concluded = cleanRows.filter(row => isConcluded(row.statusOriginal)).length;
  const inProgress = cleanRows.filter(row => isInProgress(row.statusOriginal)).length;
  const blocked = cleanRows.filter(row => isBlocked(row.statusOriginal)).length;
  const notStarted = cleanRows.filter(row => isNotStarted(row.statusOriginal)).length;
  const cancelled = cleanRows.filter(row => isCancelled(row.statusOriginal)).length;
  const percent = getPercent(concluded, total);

  updateSummary(total, concluded, inProgress, notStarted, blocked, cancelled, percent);
  renderLeaderboard(cleanRows);
  renderStatusBars(total, concluded, inProgress, notStarted, blocked, cancelled);
  renderAreaBoard(cleanRows);
  renderFocusTable(cleanRows);
}

function updateSummary(total, concluded, inProgress, notStarted, blocked, cancelled, percent) {
  els.totalCenarios.textContent = total.toLocaleString('pt-BR');
  els.totalConcluidos.textContent = concluded.toLocaleString('pt-BR');
  els.totalEmAndamento.textContent = inProgress.toLocaleString('pt-BR');
  els.totalNaoIniciado.textContent = notStarted.toLocaleString('pt-BR');
  if (els.totalBloqueados) {
    els.totalBloqueados.textContent = blocked.toLocaleString('pt-BR');
  }
  if (els.totalCancelados) {
    els.totalCancelados.textContent = cancelled.toLocaleString('pt-BR');
  }
  els.globalPercent.textContent = `${formatPercent(percent)}%`;
  els.ringProgress.style.strokeDashoffset = `${RING_CIRCUMFERENCE * (1 - percent / 100)}`;

  const currentMessage = [...motivationalMessages].reverse().find(item => percent >= item.threshold) || motivationalMessages[0];
  els.motivationalTag.textContent = currentMessage.tag;
  els.headlineCallout.textContent = currentMessage.title;
  els.headlinePill.textContent = currentMessage.pill;
}

function renderLeaderboard(rows) {
  if (!rows.length) {
    els.leaderboard.innerHTML = 'Nenhum dado disponível.';
    return;
  }

  const grouped = new Map();

  rows.forEach(row => {
    const key = row.lider || 'Sem líder';
    if (!grouped.has(key)) {
      grouped.set(key, { lider: key, total: 0, concluded: 0, inProgress: 0 });
    }
    const item = grouped.get(key);
    item.total += 1;
    if (isConcluded(row.statusOriginal)) item.concluded += 1;
    if (isInProgress(row.statusOriginal)) item.inProgress += 1;
  });

  const ranking = [...grouped.values()]
    .map(item => ({ ...item, percent: getPercent(item.concluded, item.total) }))
    .sort((a, b) => b.concluded - a.concluded || b.percent - a.percent || a.lider.localeCompare(b.lider, 'pt-BR'))
    .slice(0, 21);

  const champion = ranking[0];
  const chasers = ranking.slice(1);

  const championHtml = champion ? `
    <div class="leader-spotlight">
      <div class="leader-spotlight-top">
        <div>
          <div class="leader-crown">1º lugar · líder da rodada</div>
          <h4 class="leader-spotlight-name">${escapeHtml(champion.lider)}</h4>
          <div class="leader-spotlight-meta">
            ${champion.concluded} concluídos de ${champion.total} cenários · ${champion.inProgress} em andamento
          </div>
        </div>
        <div class="leader-spotlight-score">
          <strong>${formatPercent(champion.percent)}%</strong>
          <span>aproveitamento</span>
        </div>
      </div>
      <div class="leader-spotlight-track">
        <div class="leader-spotlight-fill" style="width:${champion.percent}%"></div>
      </div>
    </div>
  ` : '';

  const chasersHtml = chasers.length ? `
    <div class="leaderboard-chasers">
      ${chasers.map((item, index) => `
        <div class="chaser-card ${index === 0 ? 'top-2' : ''} ${index === 1 ? 'top-3' : ''}">
          <div class="chaser-head">
            <div>
              <div class="chaser-place">${index + 2}º</div>
            </div>
            <div class="chaser-score">
              <strong>${formatPercent(item.percent)}%</strong>
              <span>aproveitamento</span>
            </div>
          </div>
          <div class="chaser-name">${escapeHtml(item.lider)}</div>
          <div class="chaser-meta">${item.concluded} concluídos · ${item.total} cenários · ${item.inProgress} em andamento</div>
        </div>
      `).join('')}
    </div>
  ` : '';

  els.leaderboard.innerHTML = `
    <div class="leaderboard-stage">
      ${championHtml}
      ${chasersHtml}
    </div>
  `;
}

function renderStatusBars(total, concluded, inProgress, notStarted, blocked, cancelled) {
  const other = Math.max(total - concluded - inProgress - notStarted - blocked - cancelled, 0);
  const statuses = [
    { label: 'Concluído', value: concluded, percent: getPercent(concluded, total), color: 'linear-gradient(90deg, #14d3a6, #7dffd8)' },
    { label: 'Em andamento', value: inProgress, percent: getPercent(inProgress, total), color: 'linear-gradient(90deg, #ffb84d, #ffd88d)' },
    { label: 'Bloqueado', value: blocked, percent: getPercent(blocked, total), color: 'linear-gradient(90deg, #ff4d6d, #ff8fa3)' },
    { label: 'Não iniciado', value: notStarted, percent: getPercent(notStarted, total), color: 'linear-gradient(90deg, #7c5cff, #b7a6ff)' },
    { label: 'Cancelado', value: cancelled, percent: getPercent(cancelled, total), color: 'linear-gradient(90deg, #98a7d8, #cad5ff)' },
    { label: 'Outros', value: other, percent: getPercent(other, total), color: 'linear-gradient(90deg, #8a94a6, #c6ccd8)' }
  ];

  els.statusBars.innerHTML = statuses.map(item => `
    <div class="status-item">
      <div class="status-head">
        <strong>${item.label}</strong>
        <span>${item.value} · ${formatPercent(item.percent)}%</span>
      </div>
      <div class="status-track">
        <div class="status-fill" style="width:${item.percent}%; background:${item.color}"></div>
      </div>
    </div>
  `).join('');
}

function renderAreaBoard(rows) {
  if (!rows.length) {
    els.areaBoard.innerHTML = 'Nenhum dado disponível.';
    return;
  }

  const grouped = new Map();
  rows.forEach(row => {
    const key = row.area || 'Não informada';
    if (!grouped.has(key)) {
      grouped.set(key, { area: key, total: 0, concluded: 0, leaders: new Set() });
    }
    const item = grouped.get(key);
    item.total += 1;
    if (isConcluded(row.statusOriginal)) item.concluded += 1;
    item.leaders.add(row.lider || 'Sem líder');
  });

  const cards = [...grouped.values()]
    .map(item => ({ ...item, percent: getPercent(item.concluded, item.total), leaderCount: item.leaders.size }))
    .sort((a, b) => b.percent - a.percent || b.concluded - a.concluded || a.area.localeCompare(b.area, 'pt-BR'))
    .slice(0, 12);

  els.areaBoard.innerHTML = cards.map(item => `
    <div class="area-card">
      <div class="area-top">
        <div class="area-title">${escapeHtml(item.area)}</div>
        <div class="area-badge">${formatPercent(item.percent)}%</div>
      </div>
      <div class="status-track" style="margin-top:12px;">
        <div class="status-fill" style="width:${item.percent}%; background: linear-gradient(90deg, #7c5cff, #14d3a6);"></div>
      </div>
      <div class="area-stats">
        <span>${item.concluded}/${item.total} concluídos</span>
        <span>${item.leaderCount} líder(es)</span>
      </div>
    </div>
  `).join('');
}

function renderFocusTable(rows) {
  const priorityRows = rows
    .filter(row => isBlocked(row.statusOriginal) || isNotStarted(row.statusOriginal))
    .sort((a, b) => compareStatusForUnlock(a.statusOriginal, b.statusOriginal) || comparePriority(a.prioridade, b.prioridade) || b.execucoes - a.execucoes || a.cenario.localeCompare(b.cenario, 'pt-BR'))
    .slice(0, 21);

  if (!priorityRows.length) {
    els.focusTable.innerHTML = '<tr><td colspan="5" class="empty-cell">Sem bloqueados ou não iniciados no momento. A pista limpou.</td></tr>';
    return;
  }

  els.focusTable.innerHTML = priorityRows.map(row => `
    <tr>
      <td>${escapeHtml(row.identificador || '-')}</td>
      <td>${escapeHtml(row.cenario || '-')}</td>
      <td>${escapeHtml(row.lider || '-')}</td>
      <td>${escapeHtml(row.area || '-')}</td>
      <td>${statusPill(row.statusOriginal)}</td>
    </tr>
  `).join('');
}

function isConcluded(status) {
  return normalize(status).includes('concluido');
}

function isInProgress(status) {
  const s = normalize(status);
  return s.includes('andamento') || s.includes('em execucao') || s.includes('em progresso');
}

function isBlocked(status) {
  const s = normalize(status);
  return s.includes('bloqueado') || s.includes('impedimento') || s.includes('travado');
}

function isNotStarted(status) {
  const s = normalize(status);
  return s.includes('nao iniciado') || s.includes('não iniciado');
}

function isCancelled(status) {
  const s = normalize(status);
  return s.includes('cancelado') || s.includes('cancelada') || s.includes('cancel');
}

function compareStatusForUnlock(a, b) {
  const weight = status => {
    if (isBlocked(status)) return 2;
    if (isNotStarted(status)) return 1;
    return 0;
  };

  return weight(b) - weight(a);
}

function getPercent(value, total) {
  return total ? (value / total) * 100 : 0;
}

function formatPercent(value) {
  return Number(value || 0).toLocaleString('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function comparePriority(a, b) {
  const pa = extractPriorityNumber(a);
  const pb = extractPriorityNumber(b);
  return pb - pa;
}

function extractPriorityNumber(value) {
  const match = String(value || '').match(/\d+/);
  return match ? Number(match[0]) : -1;
}

function statusPill(status) {
  const label = escapeHtml(status || '-');
  let className = 'neutral';

  if (isConcluded(status)) className = 'status-concluido';
  else if (isInProgress(status)) className = 'status-andamento';
  else if (isNotStarted(status)) className = 'status-nao-iniciado';
  else if (isCancelled(status)) className = 'status-cancelado';
  else className = 'status-outro';

  return `<span class="status-pill ${className}">${label}</span>`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}