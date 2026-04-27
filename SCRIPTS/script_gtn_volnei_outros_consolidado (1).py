from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime
import pandas as pd
import subprocess
import os
import time
import traceback
import unicodedata
import re

load_dotenv()

GTN_URL = os.getenv("GTN_URL", "https://gtn.ninecon.com.br/ords/r/gtn/gtn/login")
GTN_HOME_URL = os.getenv("GTN_HOME_URL", "https://gtn.ninecon.com.br/ords/r/gtn/gtn/home")
GTN_USER = os.getenv("GTN_USER")
GTN_PASS = os.getenv("GTN_PASS")

# Região do relatório interativo no APEX
REGION_ID = "R35932200234408468"

# Líder separado em arquivo próprio
LIDER_VOLNEI = os.getenv("GTN_LIDER_VOLNEI", "Volnei Pereira")

# Lista base dos líderes que serão baixados.
# O script baixa primeiro o Volnei Pereira e depois todos os demais desta lista.
LIDERES_FILTRO = os.getenv(
    "GTN_LIDERES",
    "Kelvin Junior,Volnei Pereira,Dalton Skajko Sales,Cezar Augusto,Carmo Silva,Dirceu Ribeiro,Edineia Pilonetto,Jackeline Dallagnol,Kleber Cadamuro,Leila Raber,Luiz Antonio Carrasco Junior,Maiara Boncoski,Luiz Antonio Rodrigues"
)

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
DOWNLOAD_DIR = BASE_DIR / "downloads"
DASHBOARD_DIR = BASE_DIR / "dashboard_data"
LOCK_FILE = BASE_DIR / "rodando.lock"
LOG_FILE = BASE_DIR / "execucao_pontual.log"

OUTPUT_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)
DASHBOARD_DIR.mkdir(exist_ok=True)


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


def limpar_texto(texto: str) -> str:
    """Remove acentos e caracteres ruins para salvar nomes de arquivos sem dor de cabeça."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"[^A-Za-z0-9_.-]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return texto or "arquivo"


def montar_lideres_outros() -> str:
    lideres = [x.strip() for x in LIDERES_FILTRO.split(",") if x.strip()]
    lideres_outros = [x for x in lideres if x.casefold() != LIDER_VOLNEI.casefold()]

    if not lideres_outros:
        raise ValueError(
            "A lista de outros líderes ficou vazia. Verifique GTN_LIDERES e GTN_LIDER_VOLNEI no .env."
        )

    return ",".join(lideres_outros)


def salvar_debug(page, nome_base: str) -> None:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    screenshot_path = OUTPUT_DIR / f"{nome_base}_{timestamp}.png"
    html_path = OUTPUT_DIR / f"{nome_base}_{timestamp}.html"

    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")
        log(f"📸 Screenshot salvo em: {screenshot_path}")
        log(f"📝 HTML salvo em: {html_path}")
    except Exception as e:
        log(f"⚠️ Falha ao salvar debug: {e}")


def aguardar_estabilidade(page, motivo: str = "") -> None:
    if motivo:
        log(f"⏳ Aguardando estabilidade: {motivo}")

    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass

    try:
        page.locator(".u-Processing, .a-Processing, .t-Processing").first.wait_for(
            state="hidden",
            timeout=15000
        )
    except Exception:
        pass

    try:
        page.wait_for_function(
            """
            () => {
                if (!window.apex || !window.apex.jQuery) return true;
                return window.apex.jQuery.active === 0;
            }
            """,
            timeout=15000
        )
    except Exception:
        pass

    page.wait_for_timeout(1200)


def fazer_login(page) -> None:
    log("🌐 Abrindo tela de login...")
    page.goto(GTN_URL, wait_until="domcontentloaded", timeout=60000)

    log("🔐 Preenchendo credenciais...")
    page.get_by_role("textbox", name="Usuário").click()
    page.get_by_role("textbox", name="Usuário").fill(GTN_USER)
    page.get_by_role("textbox", name="Senha").fill(GTN_PASS)

    log("➡️ Clicando em Acessar...")
    page.get_by_role("button", name="Acessar").click()

    aguardar_estabilidade(page, "pós-login")
    log(f"✅ Login concluído. URL atual: {page.url}")

    if "login" in page.url.lower():
        log("ℹ️ Ainda na tela de login. Tentando abrir home...")
        page.goto(GTN_HOME_URL, wait_until="domcontentloaded", timeout=60000)
        aguardar_estabilidade(page, "abertura da home")
        log(f"✅ Home aberta. URL atual: {page.url}")


def abrir_execucao_testes(page) -> None:
    log("📂 Abrindo grupo do programa...")
    page.get_by_label("Exibição em Grade").get_by_role(
        "link",
        name="GRUPO PLUMA - PROGRAMA CONECTA"
    ).click()

    aguardar_estabilidade(page, "grupo do programa")

    log("🧭 Abrindo navegação principal...")
    page.get_by_role("button", name="Navegação Principal").click()

    log("🌲 Expandindo árvore...")
    page.locator(".a-TreeView-toggle").first.click()

    log("🧪 Entrando em Execução de Testes...")
    page.get_by_role("treeitem", name="Execução de Testes").click()

    aguardar_estabilidade(page, "tela de execução")
    log(f"✅ Tela de execução carregada: {page.url}")


def tentar_resetar_relatorio(page) -> None:
    """
    Tenta limpar filtros anteriores do relatório antes de aplicar o próximo filtro.
    Isso evita o erro clássico: baixar Volnei e depois aplicar "outros" por cima,
    gerando interseção vazia ou CSV repetido.
    """
    log("♻️ Limpando filtros anteriores do relatório...")

    # Tentativa 1: API JavaScript nativa do APEX para Interactive Report.
    try:
        page.evaluate(
            f"""
            () => {{
                if (window.apex && apex.region("{REGION_ID}")) {{
                    apex.region("{REGION_ID}").call("reset");
                    return true;
                }}
                return false;
            }}
            """
        )
        aguardar_estabilidade(page, "reset via API APEX")
        log("✅ Reset do relatório executado via API APEX.")
        return
    except Exception as e:
        log(f"⚠️ Reset via API APEX falhou: {e}")

    # Tentativa 2: menu visual do APEX.
    try:
        page.get_by_role("button", name="Ações").click()
        page.get_by_role("menuitem", name=re.compile("Relat.rio|Report", re.I)).click()
        page.get_by_role("menuitem", name=re.compile("Redefinir|Reset", re.I)).click()
        aguardar_estabilidade(page, "reset via menu")
        log("✅ Reset do relatório executado pelo menu.")
        return
    except Exception as e:
        log(f"⚠️ Reset pelo menu não executado: {e}")
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

    log("ℹ️ Não foi possível confirmar reset visual. O script seguirá aplicando o filtro solicitado.")


def aplicar_filtro_lideres(page, lideres_expr: str, descricao: str) -> None:
    log(f"🔎 Abrindo filtro para: {descricao}")
    page.get_by_role("button", name="Ações").click()
    page.get_by_role("menuitem", name="Filtrar").click()

    log("🧩 Selecionando coluna LIDER_CENARIO...")
    page.locator(f"#{REGION_ID}_column_name").select_option("LIDER_CENARIO")

    log("🧩 Selecionando operador IN...")
    page.locator(f"#{REGION_ID}_STRING_OPT").select_option("in")

    log(f"🧾 Preenchendo expressão ({descricao}): {lideres_expr}")
    page.get_by_role("textbox", name="Expressão").click()
    page.get_by_role("textbox", name="Expressão").fill(lideres_expr)

    log("✅ Aplicando filtro...")
    page.get_by_role("button", name="Aplicar").click()
    aguardar_estabilidade(page, f"aplicação do filtro {descricao}")


def ajustar_quantidade_linhas(page) -> None:
    log("📄 Ajustando quantidade de linhas para 100000...")
    page.get_by_label("Linhas", exact=True).select_option("100000")
    aguardar_estabilidade(page, "ajuste de linhas")


def exportar_csv(page, prefixo: str) -> Path:
    log(f"📤 Abrindo menu de download para: {prefixo}")
    page.get_by_role("button", name="Ações").click()
    page.get_by_role("menuitem", name="Fazer Download").click()

    log("📄 Selecionando formato CSV...")
    page.get_by_role("option", name="CSV").click()

    log("⬇️ Iniciando download...")
    with page.expect_download(timeout=60000) as download_info:
        page.get_by_role("button", name="Fazer Download").click()

    download = download_info.value

    erro_download = download.failure()
    if erro_download:
        raise RuntimeError(f"Falha no download: {erro_download}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_original = download.suggested_filename or "Cenarios_Consolidados.csv"
    nome_limpo = limpar_texto(nome_original.replace(" ", "_"))
    prefixo_limpo = limpar_texto(prefixo)
    destino = DOWNLOAD_DIR / f"{timestamp}_{prefixo_limpo}_{nome_limpo}"

    download.save_as(str(destino))
    log(f"✅ CSV salvo em: {destino}")

    try:
        page.get_by_role("button", name="Fechar").click(timeout=3000)
        log("🪟 Janela de download fechada.")
    except Exception:
        log("ℹ️ Botão Fechar não apareceu, seguindo o fluxo.")

    aguardar_estabilidade(page, "pós-download")
    return destino


def baixar_arquivo_por_lideres(page, lideres_expr: str, descricao: str) -> Path:
    tentar_resetar_relatorio(page)
    aplicar_filtro_lideres(page, lideres_expr, descricao)
    ajustar_quantidade_linhas(page)
    return exportar_csv(page, descricao)


def ler_csv_flexivel(arquivo_entrada: Path) -> pd.DataFrame:
    tentativas = [
        {"sep": ";", "encoding": "utf-8-sig"},
        {"sep": ";", "encoding": "latin1"},
        {"sep": ",", "encoding": "utf-8-sig"},
        {"sep": ",", "encoding": "latin1"},
        {"sep": "\t", "encoding": "utf-8-sig"},
        {"sep": "\t", "encoding": "latin1"},
    ]

    ultimo_erro = None

    for tentativa in tentativas:
        try:
            df = pd.read_csv(
                arquivo_entrada,
                sep=tentativa["sep"],
                encoding=tentativa["encoding"]
            )

            # Evita falso positivo quando o CSV inteiro vem em uma coluna por separador errado.
            if len(df.columns) <= 1:
                raise ValueError("CSV lido com apenas uma coluna. Separador provavelmente incorreto.")

            log(
                f"✅ CSV lido: {arquivo_entrada.name} | "
                f"sep='{tentativa['sep']}' | encoding='{tentativa['encoding']}' | "
                f"linhas={len(df)}"
            )
            return df

        except Exception as e:
            ultimo_erro = e

    raise RuntimeError(f"Não consegui ler o CSV {arquivo_entrada}. Último erro: {ultimo_erro}")


def validar_coluna_lider(df: pd.DataFrame, origem: str) -> None:
    if "LIDER_CENARIO" in df.columns:
        coluna = "LIDER_CENARIO"
    elif "Líder do Cenário" in df.columns:
        coluna = "Líder do Cenário"
    elif "Lider do Cenário" in df.columns:
        coluna = "Lider do Cenário"
    elif "Lider do Cenario" in df.columns:
        coluna = "Lider do Cenario"
    else:
        log(f"⚠️ Não encontrei coluna de líder em {origem}. Seguindo sem validação por líder.")
        return

    total = len(df)
    volnei = df[coluna].astype(str).str.strip().str.casefold().eq(LIDER_VOLNEI.casefold()).sum()
    log(f"📊 Validação {origem}: linhas={total} | {LIDER_VOLNEI}={volnei} | outros={total - volnei}")


def consolidar_csvs_para_dashboard(arquivos_entrada: list[Path]) -> Path:
    log("🧹 Consolidando CSVs baixados para o dashboard principal...")

    dataframes = []

    for arquivo in arquivos_entrada:
        df = ler_csv_flexivel(arquivo)
        validar_coluna_lider(df, arquivo.name)
        dataframes.append(df)

    if not dataframes:
        raise RuntimeError("Nenhum CSV informado para consolidar.")

    df_final = pd.concat(dataframes, ignore_index=True, sort=False)

    linhas_antes = len(df_final)
    df_final = df_final.drop_duplicates()
    linhas_depois = len(df_final)

    if linhas_antes != linhas_depois:
        log(f"🧽 Duplicidades exatas removidas: {linhas_antes - linhas_depois}")

    gerado_em = datetime.now().strftime("%Y-%m-%d %H:%M")
    df_final["Gerado em"] = gerado_em

    arquivo_saida = DASHBOARD_DIR / "Cenarios_Consolidados_atualizado.csv"
    df_final.to_csv(arquivo_saida, sep=";", index=False, encoding="utf-8-sig")

    log(f"✅ Arquivo final gerado: {arquivo_saida}")
    log(f"📦 Total consolidado: {len(df_final)} linhas")
    log(f"🕒 Coluna 'Gerado em' preenchida com: {gerado_em}")

    log("⏳ CSVs baixados, consolidados e tratados com sucesso. Prosseguindo com envio ao Git...")

    return arquivo_saida


def rodar_git(args, cwd: Path) -> str:
    resultado = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace"
    )

    if resultado.returncode != 0:
        raise RuntimeError(
            f"Erro no git {' '.join(args)}\n"
            f"STDOUT:\n{resultado.stdout}\n"
            f"STDERR:\n{resultado.stderr}"
        )

    return resultado.stdout.strip()


def commitar_e_enviar_arquivo(repo_dir: Path, arquivo: Path) -> None:
    rel_path = arquivo.relative_to(repo_dir)

    log(f"📌 Adicionando arquivo ao git: {rel_path}")
    rodar_git(["add", str(rel_path)], repo_dir)

    status = rodar_git(["status", "--porcelain", str(rel_path)], repo_dir)
    if not status.strip():
        log("ℹ️ Nenhuma alteração detectada. Nada para commitar.")
        return

    mensagem = f"Atualiza dashboard GTN em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    log(f"📝 Criando commit: {mensagem}")
    rodar_git(["commit", "-m", mensagem], repo_dir)

    log("🚀 Enviando para o GitHub...")
    rodar_git(["push"], repo_dir)

    log("✅ Commit e push realizados com sucesso.")


def executar_fluxo() -> None:
    validar_env()

    lideres_outros = montar_lideres_outros()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            fazer_login(page)
            abrir_execucao_testes(page)

            log("==================================================")
            log(f"⬇️ Baixando arquivo exclusivo do líder: {LIDER_VOLNEI}")
            log("==================================================")
            arquivo_volnei = baixar_arquivo_por_lideres(
                page,
                LIDER_VOLNEI,
                "VOLNEI_PEREIRA"
            )

            log("==================================================")
            log("⬇️ Baixando arquivo dos demais líderes")
            log("==================================================")
            arquivo_outros = baixar_arquivo_por_lideres(
                page,
                lideres_outros,
                "OUTROS_LIDERES"
            )

            arquivo_dashboard = consolidar_csvs_para_dashboard([arquivo_volnei, arquivo_outros])

            salvar_debug(page, "final_sucesso")
            commitar_e_enviar_arquivo(BASE_DIR, arquivo_dashboard)

            log("🎯 Processo concluído com sucesso.")
            log(f"📥 Arquivo Volnei: {arquivo_volnei}")
            log(f"📥 Arquivo outros líderes: {arquivo_outros}")
            log(f"📊 Arquivo dashboard: {arquivo_dashboard}")

        except PlaywrightTimeoutError as e:
            log(f"⏰ Timeout: {e}")
            salvar_debug(page, "timeout")
            raise

        except Exception as e:
            log(f"❌ Erro: {e}")
            salvar_debug(page, "erro")
            raise

        finally:
            context.close()
            browser.close()


def executar() -> None:
    if LOCK_FILE.exists():
        log("⚠️ Já existe uma execução em andamento. Encerrando.")
        return

    try:
        LOCK_FILE.touch()

        log("==================================================")
        log("🚀 Iniciando execução pontual do GTN")
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
