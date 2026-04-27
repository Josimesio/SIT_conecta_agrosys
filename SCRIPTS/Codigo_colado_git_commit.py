from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Page,
    Download,
)
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import time
import traceback
import csv
import hashlib
import subprocess

load_dotenv()

GTN_URL = os.getenv("GTN_URL", "https://gtn.ninecon.com.br/ords/r/gtn/gtn/login?tz=-3:00")
GTN_HOME_URL = os.getenv("GTN_HOME_URL", "https://gtn.ninecon.com.br/ords/r/gtn/gtn/home")
GTN_USER = os.getenv("GTN_USER")
GTN_PASS = os.getenv("GTN_PASS")

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
DOWNLOAD_DIR = BASE_DIR / "downloads"
LOCK_FILE = BASE_DIR / "rodando.lock"
LOG_FILE = BASE_DIR / "execucao_fluxo2.log"

OUTPUT_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

RELATORIO_POS_MODAL_ID = "36017690830433903"

RELATORIOS = [
    {"id": "80051142089712073", "nome": "relatorio_01"},
    {"id": "81391193639005695", "nome": "relatorio_02"},
]

DOWNLOAD_TIMEOUT_MS = int(os.getenv("GTN_DOWNLOAD_TIMEOUT_MS", "180000"))
DEFAULT_TIMEOUT_MS = int(os.getenv("GTN_DEFAULT_TIMEOUT_MS", "60000"))
POST_DOWNLOAD_PAUSE_MS = int(os.getenv("GTN_POST_DOWNLOAD_PAUSE_MS", "2000"))
MAX_TENTATIVAS_DOWNLOAD = int(os.getenv("GTN_MAX_TENTATIVAS_DOWNLOAD", "3"))
MAX_TENTATIVAS_APLICAR_RELATORIO = int(os.getenv("GTN_MAX_TENTATIVAS_APLICAR_RELATORIO", "3"))
APEX_REFRESH_TIMEOUT_MS = int(os.getenv("GTN_APEX_REFRESH_TIMEOUT_MS", "45000"))


def url_tem_sessao(url: str) -> bool:
    try:
        return "session=" in (url or "").lower()
    except Exception:
        return False


def log(msg: str) -> None:
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{agora}] {msg}"
    print(linha)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def validar_env() -> None:
    faltando = []

    if not GTN_USER:
        faltando.append("GTN_USER")
    if not GTN_PASS:
        faltando.append("GTN_PASS")

    if faltando:
        raise ValueError(f"Variáveis ausentes no .env: {', '.join(faltando)}")


def pagina_aberta(page: Page) -> bool:
    try:
        return (page is not None) and (not page.is_closed())
    except Exception:
        return False


def aguardar_processamento_apex(page: Page, motivo: str = "") -> None:
    if motivo:
        log(f"🌀 Aguardando refresh APEX: {motivo}")

    seletores_loading = [
        ".u-Processing",
        ".u-Processing-spinner",
        ".a-Region-loading",
        ".a-Region--loading",
        ".a-IRR-loading",
        ".a-IRR-icon--processing",
        ".js-regionIsLoading",
        "[aria-busy='true']",
    ]

    for seletor in seletores_loading:
        try:
            page.locator(seletor).first.wait_for(state="hidden", timeout=APEX_REFRESH_TIMEOUT_MS)
        except Exception:
            continue

    page.wait_for_timeout(1200)


def obter_assinatura_grade(page: Page) -> str:
    seletores = [
        "#R35932200234408468 .a-IRR-table tbody",
        "#R35932200234408468 .a-GV-table tbody",
        "#R35932200234408468 .t-Report-report tbody",
        "table.a-IRR-table tbody",
    ]

    partes = []

    for seletor in seletores:
        try:
            alvo = page.locator(seletor).first
            if alvo.is_visible(timeout=1500):
                linhas = alvo.locator("tr")
                qtd = linhas.count()
                partes.append(f"rows={qtd}")

                limite = min(qtd, 5)
                for i in range(limite):
                    try:
                        texto = linhas.nth(i).inner_text(timeout=1500).strip()
                        texto = " ".join(texto.split())
                        if texto:
                            partes.append(texto[:220])
                    except Exception:
                        continue
                break
        except Exception:
            continue

    if not partes:
        try:
            partes.append(page.locator("#R35932200234408468").first.inner_text(timeout=2000)[:800])
        except Exception:
            partes.append("(sem assinatura de grade)")

    return " | ".join(partes)


def aplicar_select_saved_report(page: Page, relatorio_id: str) -> None:
    seletor = page.locator("#R35932200234408468_saved_reports")
    seletor.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)

    try:
        seletor.select_option(relatorio_id)
    except Exception:
        page.evaluate(
            """(cfg) => {
                const el = document.querySelector(cfg.selector);
                if (!el) throw new Error('select não encontrado');
                el.value = cfg.value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            {"selector": "#R35932200234408468_saved_reports", "value": relatorio_id},
        )
        return

    try:
        seletor.dispatch_event("input")
    except Exception:
        pass

    try:
        seletor.dispatch_event("change")
    except Exception:
        pass

    try:
        page.evaluate(
            """(cfg) => {
                const el = document.querySelector(cfg.selector);
                if (!el) return;
                el.value = cfg.value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            {"selector": "#R35932200234408468_saved_reports", "value": relatorio_id},
        )
    except Exception:
        pass


def aguardar_grade_mudar(page: Page, assinatura_anterior: str, relatorio_nome: str) -> str:
    inicio = time.time()
    ultima_assinatura = assinatura_anterior

    while (time.time() - inicio) * 1000 < APEX_REFRESH_TIMEOUT_MS:
        aguardar_processamento_apex(page, f"aplicação do relatório {relatorio_nome}")
        aguardar_estabilidade(page, f"refresh do relatório {relatorio_nome}")
        atual = obter_assinatura_grade(page)
        if atual and atual != assinatura_anterior:
            return atual
        ultima_assinatura = atual
        page.wait_for_timeout(1500)

    return ultima_assinatura


def aguardar_estabilidade(page: Page, motivo: str = "") -> None:
    if motivo:
        log(f"⏳ Aguardando estabilidade: {motivo}")

    try:
        page.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
    except Exception:
        pass

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    page.wait_for_timeout(1500)


def salvar_debug(page: Page, nome_base: str) -> None:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    screenshot_path = OUTPUT_DIR / f"{nome_base}_{timestamp}.png"
    html_path = OUTPUT_DIR / f"{nome_base}_{timestamp}.html"

    try:
        if not pagina_aberta(page):
            log("⚠️ Página já estava fechada. Debug visual não pôde ser salvo.")
            return

        page.screenshot(path=str(screenshot_path), full_page=False)
        html_path.write_text(page.content(), encoding="utf-8")
        log(f"📸 Screenshot salvo em: {screenshot_path}")
        log(f"📝 HTML salvo em: {html_path}")
    except Exception as e:
        log(f"⚠️ Falha ao salvar debug: {e}")


def fechar_modal_download(page: Page) -> None:
    def aplicar_select_pos_modal() -> None:
        try:
            log(f"🎯 Aplicando seleção pós-modal no relatório {RELATORIO_POS_MODAL_ID}...")
            aplicar_select_saved_report(page, RELATORIO_POS_MODAL_ID)
            aguardar_processamento_apex(page, "seleção pós-modal")
            log("⏳ Aguardando 5 segundos após select_option pós-modal...")
            page.wait_for_timeout(5000)
        except Exception as e:
            log(f"⚠️ Falha ao aplicar select_option pós-modal: {e}")

    candidatos = [
        page.get_by_role("button", name="Fechar"),
        page.get_by_role("button", name="Cancelar"),
        page.locator("button.ui-dialog-titlebar-close"),
        page.locator(".ui-dialog-titlebar-close"),
        page.locator("button.t-Dialog-closeButton"),
        page.locator("button[aria-label='Close']"),
    ]

    for candidato in candidatos:
        try:
            if candidato.first.is_visible(timeout=1500):
                candidato.first.click(timeout=3000)
                log("🪟 Janela/modal de download fechada.")
                page.wait_for_timeout(1000)
                aplicar_select_pos_modal()
                return
        except Exception:
            continue

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        log("ℹ️ Modal não tinha botão claro. Tentei fechar com ESC.")
        aplicar_select_pos_modal()
    except Exception:
        log("ℹ️ Não foi possível fechar modal explicitamente. Seguindo o fluxo.")


def fazer_login(page: Page) -> None:
    log("🌐 Abrindo tela de login...")
    page.goto(GTN_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
    aguardar_estabilidade(page, "carregamento inicial da tela de login")

    log("🔐 Preenchendo credenciais...")
    page.get_by_role("textbox", name="Usuário").click()
    page.get_by_role("textbox", name="Usuário").fill(GTN_USER)
    page.get_by_role("textbox", name="Senha").fill(GTN_PASS)

    log("➡️ Clicando em Acessar...")
    page.get_by_role("button", name="Acessar").click()

    try:
        page.wait_for_url(lambda url: "login" not in url.lower(), timeout=DEFAULT_TIMEOUT_MS)
    except Exception:
        pass

    aguardar_estabilidade(page, "pós-login")
    log(f"✅ Pós-login. URL atual: {page.url}")

    if "login" in page.url.lower():
        salvar_debug(page, "falha_login")
        raise RuntimeError(
            "O sistema permaneceu na tela de login após o acesso. "
            "Verifique credenciais, expiração de sessão ou bloqueio do APEX."
        )

    if not url_tem_sessao(page.url):
        log("ℹ️ URL sem session explícita. Tentando validar contexto da aplicação...")
        try:
            page.goto(GTN_HOME_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
            aguardar_estabilidade(page, "validação da home após login")
            log(f"✅ Home validada. URL atual: {page.url}")
        except Exception as e:
            raise RuntimeError(f"Login aparentemente efetuado, mas a home não abriu corretamente: {e}")


def listar_botoes_visiveis(page: Page) -> None:
    try:
        botoes = page.locator("button:visible, a:visible")
        qtd = min(botoes.count(), 20)
        nomes = []
        for i in range(qtd):
            try:
                texto = botoes.nth(i).inner_text(timeout=500).strip()
                if not texto:
                    texto = (botoes.nth(i).get_attribute("aria-label") or "").strip()
                if not texto:
                    texto = (botoes.nth(i).get_attribute("title") or "").strip()
                if texto:
                    nomes.append(texto.replace("\n", " "))
            except Exception:
                continue
        if nomes:
            log(f"🔎 Ações/botões visíveis na tela: {nomes}")
    except Exception:
        pass


def tela_execucao_testes_ativa(page: Page) -> bool:
    candidatos = [
        "#R35932200234408468_saved_reports",
        "label:has-text('Linhas')",
        "button:has-text('Ações')",
    ]
    for seletor in candidatos:
        try:
            if page.locator(seletor).first.is_visible(timeout=1500):
                return True
        except Exception:
            continue
    return False


def tentar_abrir_menu_navegacao(page: Page) -> bool:
    candidatos = [
        page.get_by_role("button", name="Navegação Principal"),
        page.locator("#t_Button_navControl"),
        page.locator("button[aria-label='Navegação Principal']"),
        page.locator("button[title='Navegação Principal']"),
        page.locator("button[aria-label*='Navegação']"),
        page.locator("button[title*='Navegação']"),
        page.locator("button.t-Button--header"),
    ]

    for i, candidato in enumerate(candidatos, start=1):
        try:
            alvo = candidato.first
            if alvo.is_visible(timeout=2000):
                log(f"🧭 Abrindo navegação principal com seletor alternativo #{i}...")
                alvo.scroll_into_view_if_needed()
                alvo.click(timeout=5000, force=True)
                page.wait_for_timeout(1000)
                return True
        except Exception:
            continue

    return False


def tentar_expandir_arvore(page: Page) -> None:
    candidatos = [
        page.locator(".a-TreeView-toggle"),
        page.locator(".a-TreeView-toggle[aria-hidden='true']"),
    ]

    for candidato in candidatos:
        try:
            alvo = candidato.first
            if alvo.is_visible(timeout=1500):
                log("🌲 Expandindo árvore...")
                alvo.scroll_into_view_if_needed()
                alvo.click(timeout=5000, force=True)
                page.wait_for_timeout(800)
                return
        except Exception:
            continue

    log("ℹ️ Não encontrei toggle da árvore. Vou tentar achar 'Execução de Testes' direto.")


def tentar_abrir_execucao_testes_pelo_menu(page: Page) -> bool:
    candidatos = [
        page.get_by_role("treeitem", name="Execução de Testes"),
        page.get_by_role("link", name="Execução de Testes"),
        page.get_by_text("Execução de Testes", exact=True),
        page.locator("a:has-text('Execução de Testes')"),
        page.locator("span:has-text('Execução de Testes')"),
    ]

    for i, candidato in enumerate(candidatos, start=1):
        try:
            alvo = candidato.first
            if alvo.is_visible(timeout=2500):
                log(f"🧪 Entrando em Execução de Testes com seletor alternativo #{i}...")
                alvo.scroll_into_view_if_needed()
                alvo.click(timeout=8000, force=True)
                aguardar_estabilidade(page, "entrada em Execução de Testes")
                return True
        except Exception:
            continue

    return False


def abrir_execucao_testes(page: Page) -> None:
    if tela_execucao_testes_ativa(page):
        log("✅ Tela de Execução de Testes já está ativa. Seguindo o fluxo.")
        return

    log(f"🔎 URL atual antes de abrir menu: {page.url}")

    if not url_tem_sessao(page.url):
        raise RuntimeError(
            "A URL atual não contém sessão válida do APEX. O login não ficou persistido na navegação."
        )

    aguardar_estabilidade(page, "estado atual após login")

    if tela_execucao_testes_ativa(page):
        log("✅ Tela de Execução de Testes ficou disponível sem precisar navegar de novo.")
        return

    menu_aberto = tentar_abrir_menu_navegacao(page)
    if not menu_aberto:
        listar_botoes_visiveis(page)
        salvar_debug(page, "sem_menu_no_estado_atual")
        raise RuntimeError(
            "Não encontrei o botão/menu de navegação principal no estado atual da página. "
            "Não vou redirecionar para HOME sem session para não derrubar o login."
        )

    tentar_expandir_arvore(page)

    if not tentar_abrir_execucao_testes_pelo_menu(page):
        listar_botoes_visiveis(page)
        salvar_debug(page, "menu_sem_execucao_testes")
        raise RuntimeError("Não encontrei a opção 'Execução de Testes' no menu lateral.")

    if not tela_execucao_testes_ativa(page):
        salvar_debug(page, "execucao_testes_nao_confirmada")
        raise RuntimeError(
            "Cliquei em 'Execução de Testes', mas a tela esperada não ficou disponível."
        )

    log(f"✅ Tela de execução carregada: {page.url}")


def selecionar_relatorio(page: Page, relatorio_id: str, relatorio_nome: str) -> None:
    log(f"📑 Selecionando relatório {relatorio_nome} ({relatorio_id})...")
    seletor = page.locator("#R35932200234408468_saved_reports")
    seletor.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    seletor.select_option(relatorio_id)
    aguardar_estabilidade(page, f"seleção do relatório {relatorio_nome}")

    valor_atual = ""
    try:
        valor_atual = seletor.input_value(timeout=3000).strip()
    except Exception:
        pass

    texto_atual = obter_texto_relatorio_selecionado(page)
    log(f"🧾 Relatório selecionado na tela -> id atual: {valor_atual or '(indisponível)'} | nome visível: {texto_atual}")

    if valor_atual and valor_atual != relatorio_id:
        raise RuntimeError(
            f"O select não confirmou o ID esperado. Esperado: {relatorio_id} | Atual na tela: {valor_atual}"
        )


def obter_texto_relatorio_selecionado(page: Page) -> str:
    try:
        seletor = page.locator("#R35932200234408468_saved_reports")
        texto = seletor.locator("option:checked").first.inner_text(timeout=3000).strip()
        return texto
    except Exception:
        return "(não foi possível obter o nome visível do relatório selecionado)"


def calcular_hash_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def contar_linhas_csv(caminho: Path) -> int:
    with abrir_csv_com_encoding_flexivel(caminho) as entrada:
        amostra = entrada.read(4096)
        entrada.seek(0)

        try:
            dialect = csv.Sniffer().sniff(amostra, delimiters=",;\t|")
        except Exception:
            dialect = csv.excel
            dialect.delimiter = ";" if ";" in amostra else ","

        reader = csv.reader(entrada, dialect)
        try:
            next(reader)
        except StopIteration:
            return 0

        return sum(1 for linha in reader if any((col or '').strip() for col in linha))


def ajustar_quantidade_linhas(page: Page) -> None:
    log("📄 Ajustando quantidade de linhas para 100000...")
    linhas = page.get_by_label("Linhas", exact=True)
    linhas.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    linhas.select_option("100000")
    try:
        linhas.dispatch_event("change")
    except Exception:
        pass
    aguardar_processamento_apex(page, "ajuste da quantidade de linhas")
    aguardar_estabilidade(page, "ajuste da quantidade de linhas")


def abrir_download_csv(page: Page) -> None:
    log("📤 Abrindo menu de download...")
    acoes = page.get_by_role("button", name="Ações")
    acoes.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    acoes.click(timeout=10000, force=True)
    page.wait_for_timeout(800)

    log("📄 Selecionando opção de download...")
    page.get_by_role("menuitem", name="Fazer Download").click(timeout=10000, force=True)
    page.wait_for_timeout(1200)

    try:
        csv_option = page.get_by_role("option", name="CSV")
        csv_option.click(timeout=4000, force=True)
        log("✅ Formato CSV selecionado explicitamente.")
        page.wait_for_timeout(500)
    except Exception:
        try:
            csv_radio = page.get_by_label("CSV", exact=True)
            csv_radio.check(timeout=3000)
            log("✅ Formato CSV marcado via label.")
            page.wait_for_timeout(500)
        except Exception:
            log("ℹ️ Opção CSV não apareceu explicitamente. Seguindo com o padrão da tela.")


def coletar_indicios_apos_clique(page: Page) -> None:
    try:
        dialogos = page.locator(".ui-dialog, .t-Dialog, [role='dialog']")
        qtd = dialogos.count()
        log(f"🔎 Diálogos visíveis após clique: {qtd}")
    except Exception:
        pass

    try:
        botoes = page.locator("button:visible")
        qtd = min(botoes.count(), 12)
        nomes = []
        for i in range(qtd):
            texto = botoes.nth(i).inner_text(timeout=1000).strip()
            if texto:
                nomes.append(texto.replace("\n", " "))
        if nomes:
            log(f"🔎 Botões visíveis: {nomes}")
    except Exception:
        pass


def esperar_download_com_fallback(page: Page, relatorio_nome: str) -> Download:
    botao_download = page.get_by_role("button", name="Fazer Download")
    botao_download.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)

    ultimo_erro = None

    for tentativa in range(1, MAX_TENTATIVAS_DOWNLOAD + 1):
        log(f"⬇️ Tentativa {tentativa}/{MAX_TENTATIVAS_DOWNLOAD} de download para {relatorio_nome}...")

        try:
            with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
                botao_download.click(timeout=10000, force=True)
            download = download_info.value
            log(f"✅ Evento de download capturado para {relatorio_nome}.")
            return download

        except PlaywrightTimeoutError as e:
            ultimo_erro = e
            log(f"⚠️ Timeout aguardando download do {relatorio_nome} na tentativa {tentativa}.")
            coletar_indicios_apos_clique(page)
            salvar_debug(page, f"timeout_download_{relatorio_nome}_tentativa_{tentativa}")

            try:
                popup = page.context.wait_for_event("page", timeout=5000)
                popup.wait_for_load_state("domcontentloaded", timeout=10000)
                log(f"🪟 Popup detectado após clique. URL: {popup.url}")
                try:
                    with popup.expect_download(timeout=15000) as download_info:
                        popup.wait_for_timeout(2000)
                    download = download_info.value
                    log(f"✅ Download capturado via popup para {relatorio_nome}.")
                    return download
                except Exception:
                    log("ℹ️ Popup apareceu, mas não entregou download automaticamente.")
            except Exception:
                log("ℹ️ Nenhum popup detectado após a tentativa.")

            try:
                page.wait_for_timeout(3000)
                if botao_download.is_visible(timeout=1000):
                    log("ℹ️ Botão de download continua visível. Reabrindo fluxo para nova tentativa.")
                else:
                    log("ℹ️ Botão de download sumiu após clique. Pode ter havido refresh/modal.")
            except Exception:
                pass

            if tentativa < MAX_TENTATIVAS_DOWNLOAD:
                fechar_modal_download(page)
                abrir_download_csv(page)

    raise RuntimeError(
        f"Nenhum download foi disparado para {relatorio_nome} após {MAX_TENTATIVAS_DOWNLOAD} tentativas. Último erro: {ultimo_erro}"
    )


def baixar_relatorio(page: Page, relatorio_nome: str) -> Path:
    abrir_download_csv(page)
    log(f"⬇️ Iniciando rotina blindada de download do relatório {relatorio_nome}...")

    download = esperar_download_com_fallback(page, relatorio_nome)

    erro_download = download.failure()
    if erro_download:
        raise RuntimeError(f"Falha no download do relatório {relatorio_nome}: {erro_download}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_original = download.suggested_filename or f"{relatorio_nome}.csv"
    nome_limpo = nome_original.replace(" ", "_")
    destino = DOWNLOAD_DIR / f"{timestamp}_{relatorio_nome}_{nome_limpo}"

    download.save_as(str(destino))
    log(f"✅ Download salvo em: {destino}")

    fechar_modal_download(page)
    page.wait_for_timeout(POST_DOWNLOAD_PAUSE_MS)
    return destino


def processar_relatorios(page: Page) -> list[Path]:
    arquivos_baixados = []
    hashes_anteriores: dict[str, dict[str, str | int]] = {}

    for indice, relatorio in enumerate(RELATORIOS, start=1):
        log("--------------------------------------------------")
        log(f"🚚 Processando relatório {indice}/{len(RELATORIOS)}: {relatorio['nome']}")
        selecionar_relatorio(page, relatorio["id"], relatorio["nome"])
        ajustar_quantidade_linhas(page)

        try:
            arquivo = baixar_relatorio(page, relatorio["nome"])
            arquivos_baixados.append(arquivo)

            hash_atual = calcular_hash_arquivo(arquivo)
            linhas_atuais = contar_linhas_csv(arquivo)
            log(f"🧮 {arquivo.name} -> linhas de dados: {linhas_atuais} | hash: {hash_atual[:16]}")

            if hash_atual in hashes_anteriores:
                anterior = hashes_anteriores[hash_atual]
                log(
                    "🚨 CSV repetido detectado! "
                    f"{arquivo.name} está idêntico ao arquivo {anterior['arquivo']} "
                    f"(relatório {anterior['relatorio']}, {anterior['linhas']} linhas)."
                )
            else:
                hashes_anteriores[hash_atual] = {
                    "arquivo": arquivo.name,
                    "relatorio": relatorio["nome"],
                    "linhas": linhas_atuais,
                }

        except Exception as e:
            log(f"❌ Falha ao baixar {relatorio['nome']}: {e}")
            salvar_debug(page, f"falha_{relatorio['nome']}")
            raise

    return arquivos_baixados


def abrir_csv_com_encoding_flexivel(caminho: Path):
    encodings_teste = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    ultimo_erro = None

    for encoding in encodings_teste:
        try:
            f = open(caminho, "r", newline="", encoding=encoding)
            f.read(4096)
            f.seek(0)
            log(f"🔤 Lendo {caminho.name} com encoding: {encoding}")
            return f
        except UnicodeDecodeError as e:
            ultimo_erro = e
            try:
                f.close()
            except Exception:
                pass
            continue

    raise RuntimeError(
        f"Não foi possível ler o CSV {caminho.name} com os encodings suportados. Último erro: {ultimo_erro}"
    )


def obter_timestamp_geracao() -> str:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M")


def consolidar_csvs(arquivos_csv: list[Path]) -> Path:
    if not arquivos_csv:
        raise RuntimeError("Nenhum CSV foi baixado para consolidar.")

    destino = OUTPUT_DIR / "Cenarios_Consolidados_atualizado.csv"
    total_linhas = 0
    cabecalho_base = None
    gerado_em = obter_timestamp_geracao()

    with open(destino, "w", newline="", encoding="utf-8-sig") as saida:
        writer = None

        for arquivo in arquivos_csv:
            if not arquivo.exists():
                log(f"⚠️ Arquivo não encontrado para consolidação: {arquivo}")
                continue

            log(f"🧩 Consolidando arquivo: {arquivo.name}")

            with abrir_csv_com_encoding_flexivel(arquivo) as entrada:
                amostra = entrada.read(4096)
                entrada.seek(0)

                try:
                    dialect = csv.Sniffer().sniff(amostra, delimiters=",;\t|")
                except Exception:
                    dialect = csv.excel
                    dialect.delimiter = ";" if ";" in amostra else ","

                reader = csv.reader(entrada, dialect)

                try:
                    cabecalho_atual = next(reader)
                except StopIteration:
                    log(f"ℹ️ Arquivo vazio ignorado na consolidação: {arquivo.name}")
                    continue

                cabecalho_atual = [c.strip() for c in cabecalho_atual]

                if writer is None:
                    cabecalho_base = cabecalho_atual + ["Gerado em"]
                    writer = csv.writer(saida, delimiter=';')
                    writer.writerow(cabecalho_base)
                    log(f"🧱 Cabeçalho base definido com {len(cabecalho_base)} colunas.")
                else:
                    if cabecalho_atual + ["Gerado em"] != cabecalho_base:
                        raise RuntimeError(
                            "Estrutura divergente entre os CSVs baixados. "
                            f"Arquivo com divergência: {arquivo.name}"
                        )

                linhas_arquivo = 0
                for linha in reader:
                    if not any((col or '').strip() for col in linha):
                        continue
                    writer.writerow(list(linha) + [gerado_em])
                    linhas_arquivo += 1
                    total_linhas += 1

                log(f"✅ {arquivo.name}: {linhas_arquivo} linhas adicionadas ao consolidado.")

    if cabecalho_base is None:
        raise RuntimeError("Os arquivos baixados não continham dados válidos para consolidar.")

    log(f"📦 Consolidado gerado em: {destino}")
    log(f"📊 Total de linhas no geral.csv: {total_linhas}")
    return destino



def executar_comando_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    processo = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    return processo.returncode, (processo.stdout or "").strip(), (processo.stderr or "").strip()


def commitar_consolidado_github(arquivo_consolidado: Path) -> None:
    if not arquivo_consolidado.exists():
        raise RuntimeError(f"Arquivo consolidado não encontrado para commit: {arquivo_consolidado}")

    repo_dir = BASE_DIR
    arquivo_relativo = arquivo_consolidado.relative_to(repo_dir)

    log(f"🐙 Preparando commit no GitHub do arquivo: {arquivo_relativo}")

    code, stdout, stderr = executar_comando_git(["git", "rev-parse", "--is-inside-work-tree"], repo_dir)
    if code != 0 or stdout.lower() != "true":
        raise RuntimeError(
            "A pasta atual não é um repositório Git válido. "
            f"Saída: {stdout or '(vazia)'} | Erro: {stderr or '(vazio)'}"
        )

    code, stdout, stderr = executar_comando_git(["git", "add", str(arquivo_relativo)], repo_dir)
    if code != 0:
        raise RuntimeError(f"Falha no git add de {arquivo_relativo}: {stderr or stdout}")

    code, stdout, stderr = executar_comando_git(
        ["git", "diff", "--cached", "--quiet", "--", str(arquivo_relativo)],
        repo_dir,
    )
    if code == 0:
        log(f"ℹ️ Nenhuma alteração detectada em {arquivo_relativo}. Commit não será criado.")
        return
    if code not in (0, 1):
        raise RuntimeError(f"Falha ao verificar alterações staged: {stderr or stdout}")

    agora_sp = datetime.now(ZoneInfo("America/Sao_Paulo"))
    mensagem_commit = (
        f"Atualiza Cenarios_Consolidados_atualizado.csv - "
        f"{agora_sp.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    code, stdout, stderr = executar_comando_git(
        ["git", "commit", "-m", mensagem_commit, "--", str(arquivo_relativo)],
        repo_dir,
    )
    if code != 0:
        raise RuntimeError(f"Falha no git commit: {stderr or stdout}")

    log(f"✅ Commit criado com sucesso. Mensagem: {mensagem_commit}")

    code, stdout, stderr = executar_comando_git(["git", "push"], repo_dir)
    if code != 0:
        raise RuntimeError(f"Falha no git push: {stderr or stdout}")

    log("🚀 Push enviado com sucesso para o GitHub.")

def executar_fluxo() -> None:
    validar_env()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-dev-shm-usage",
                "--disable-popup-blocking",
            ],
        )
        context = browser.new_context(accept_downloads=True)
        context.set_default_timeout(DEFAULT_TIMEOUT_MS)
        page = context.new_page()

        try:
            fazer_login(page)
            abrir_execucao_testes(page)

            arquivos_baixados = processar_relatorios(page)
            arquivo_consolidado = consolidar_csvs(arquivos_baixados)

            salvar_debug(page, "final_sucesso")

            log("🎯 Processo concluído com sucesso.")
            for arquivo in arquivos_baixados:
                log(f"📥 Arquivo baixado: {arquivo}")
            log(f"🗂️ Arquivo consolidado final: {arquivo_consolidado}")
            commitar_consolidado_github(arquivo_consolidado)

        except PlaywrightTimeoutError as e:
            log(f"⏰ Timeout: {e}")
            salvar_debug(page, "timeout")
            raise

        except Exception as e:
            log(f"❌ Erro: {e}")
            salvar_debug(page, "erro")
            raise

        finally:
            try:
                context.close()
            finally:
                browser.close()


def executar() -> None:
    if LOCK_FILE.exists():
        log("⚠️ Já existe uma execução em andamento. Encerrando.")
        return

    try:
        LOCK_FILE.touch()

        log("==================================================")
        log("🚀 Iniciando execução do fluxo 2 GTN")
        log("==================================================")

        executar_fluxo()

        log("✅ Execução encerrada com sucesso.")

    except Exception as e:
        log(f"❌ Falha geral na execução: {e}")
        log(traceback.format_exc())

    finally:
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except Exception as e:
            log(f"⚠️ Não consegui remover lock file: {e}")


if __name__ == "__main__":
    executar()
    
    