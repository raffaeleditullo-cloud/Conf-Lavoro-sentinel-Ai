"""
CONF-LAVORO SENTINEL AI // ORIN BRAIN — KERYX VERBALIZER
Motore Universale di Normalizzazione e Prosodia Fonetica per LLM e TTS.
Converte il testo visivo (Markdown, numeri, acronimi anglofoni, percorsi, formule)
in una traccia fonetica italiana naturale, fluida e impeccabile per ElevenLabs.
"""

import re
from typing import Optional


# =========================================================================
# 1. DIZIONARIO FONETICO ANGLO-TECNICO (Grapheme-to-Phoneme Mapping)
# =========================================================================
PHONETIC_TECH_MAP = {
    # Acronimi compitati all'inglese
    r"\bAPI\b": "ei-pi-ai",
    r"\bAPIs\b": "ei-pi-ais",
    r"\bAI\b": "ei-ai",
    r"\bUI\b": "iu-ai",
    r"\bUX\b": "iu-ecs",
    r"\bCLI\b": "si-el-ai",
    r"\bIDE\b": "ai-di-i",
    r"\bGPU\b": "gi-pi-iu",
    r"\bGPUs\b": "gi-pi-ius",
    r"\bCPU\b": "si-pi-iu",
    r"\bCPUs\b": "si-pi-ius",
    r"\bLLM\b": "el-el-em",
    r"\bLLMs\b": "el-el-ems",
    r"\bAST\b": "ei-es-ti",
    r"\bRAM\b": "Ram",
    r"\bROM\b": "Rom",
    r"\bURL\b": "u-erre-elle",
    r"\bHTTP\b": "acca-ti-ti-pi",
    r"\bHTTPS\b": "acca-ti-ti-pi-esse",
    r"\bJSON\b": "geison",
    r"\bJSONL\b": "geison-elle",
    r"\bSQL\b": "si-quel",
    r"\bSDK\b": "esse-di-kappa",
    r"\bOSINT\b": "osint",
    r"\bOHI\b": "indice di salute operativa",
    r"\bLOC\b": "righe di codice",
    r"\bBPM\b": "battiti al minuto",
    r"\bMPC\b": "emme-pi-ci",

    # Termini informatici e gergo anglosassone
    r"\bPython\b": "Paiton",
    r"\bpython\b": "paiton",
    r"\bPipeline\b": "paip-lain",
    r"\bpipeline\b": "paip-lain",
    r"\bCache\b": "cèsh",
    r"\bcache\b": "cèsh",
    r"\bTimeout\b": "taim-aut",
    r"\btimeout\b": "taim-aut",
    r"\bDeploy\b": "de-ploi",
    r"\bdeploy\b": "de-ploi",
    r"\bDeployment\b": "de-ploi-ment",
    r"\bdeployment\b": "de-ploi-ment",
    r"\bFramework\b": "freim-uork",
    r"\bframework\b": "freim-uork",
    r"\bFailover\b": "feil-over",
    r"\bfailover\b": "feil-over",
    r"\bLoop\b": "lup",
    r"\bloop\b": "lup",
    r"\bSandbox\b": "sènd-box",
    r"\bsandbox\b": "sènd-box",
    r"\bRuntime\b": "ran-taim",
    r"\bruntime\b": "ran-taim",
    r"\bBackend\b": "bèk-end",
    r"\bbackend\b": "bèk-end",
    r"\bFrontend\b": "front-end",
    r"\bfrontend\b": "front-end",
    r"\bBug\b": "bag",
    r"\bbug\b": "bag",
    r"\bBugs\b": "bags",
    r"\bbugs\b": "bags",
    r"\bDebug\b": "di-bag",
    r"\bdebug\b": "di-bag",
    r"\bDebugging\b": "di-bagghing",
    r"\bdebugging\b": "di-bagghing",
    r"\bDataset\b": "deita-set",
    r"\bdataset\b": "deita-set",
    r"\bBenchmark\b": "bènch-mark",
    r"\bbenchmark\b": "bènch-mark",
    r"\bToken\b": "tochen",
    r"\btoken\b": "tochen",
    r"\bTokens\b": "tochen",
    r"\btokens\b": "tochen",
    r"\bBatch\b": "bètch",
    r"\bbatch\b": "bètch",
    r"\bPrompt\b": "prompt",
    r"\bprompt\b": "prompt",
    r"\bScript\b": "script",
    r"\bscript\b": "script",
    r"\bScripts\b": "scripts",
    r"\bscripts\b": "scripts",
    r"\bEndpoint\b": "end-point",
    r"\bendpoint\b": "end-point",
    r"\bHook\b": "huk",
    r"\bhook\b": "huk",
    r"\bServer\b": "sèrver",
    r"\bserver\b": "sèrver",
    r"\bBootstrap\b": "but-strap",
    r"\bbootstrap\b": "but-strap",
    r"\bRepository\b": "repozitori",
    r"\brepository\b": "repozitori",
    r"\bRepo\b": "rèpo",
    r"\brepo\b": "rèpo",
    r"\bCommit\b": "còmmit",
    r"\bcommit\b": "còmmit",
    r"\bGit\b": "Ghit",
    r"\bgit\b": "ghit",
    r"\bGitHub\b": "Ghit-hab",
    r"\bgithub\b": "ghit-hab",
    r"\bOllama\b": "Ollama",
    r"\bQwen\b": "Kuen",
    r"\bqwen\b": "kuen",
    r"\bClaude\b": "Clod",
    r"\bCode\b": "Coud",
    r"\bDeepSeek\b": "Dip-sik",
    r"\bChatGPT\b": "Ciat-gi-pi-ti",
}


# =========================================================================
# 2. NUMERI ITALIANI IN LETTERE (Determinismo Matematico)
# =========================================================================
UNITA = ["", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove"]
DIECI_DICIANNOVE = ["dieci", "undici", "dodici", "tredici", "quattordici", "quindici", "sedici", "diciassette", "diciotto", "diciannove"]
DECINE = ["", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta"]


def int_to_italian_words(n: int) -> str:
    """Converte un numero intero da 0 a 999.999 in parole italiane esatte."""
    if n == 0:
        return "zero"
    if n < 0:
        return "meno " + int_to_italian_words(abs(n))

    if n < 10:
        return UNITA[n]
    if n < 20:
        return DIECI_DICIANNOVE[n - 10]
    if n < 100:
        dec = n // 10
        rem = n % 10
        dec_str = DECINE[dec]
        if rem in (1, 8):
            # Elisione vocale (ventuno, ventotto, trentuno...)
            dec_str = dec_str[:-1]
        rem_str = UNITA[rem]
        if rem == 3:
            rem_str = "tré"
        return dec_str + rem_str

    if n < 1000:
        cen = n // 100
        rem = n % 100
        cen_str = "cento" if cen == 1 else UNITA[cen] + "cento"
        rem_str = int_to_italian_words(rem) if rem > 0 else ""
        return cen_str + rem_str

    if n < 1000000:
        mil = n // 1000
        rem = n % 1000
        mil_str = "mille" if mil == 1 else int_to_italian_words(mil) + "mila"
        rem_str = int_to_italian_words(rem) if rem > 0 else ""
        return mil_str + rem_str

    # Per numeri superiori al milione
    milioni = n // 1000000
    rem = n % 1000000
    milioni_str = "un milione" if milioni == 1 else int_to_italian_words(milioni) + " milioni"
    rem_str = (" " + int_to_italian_words(rem)) if rem > 0 else ""
    return milioni_str + rem_str


# =========================================================================
# 3. RIPARAZIONE ACCENTI E CADENZA ESPRESSIVA ITALIANA
# =========================================================================
ACCENT_REPAIR_MAP = [
    (r"\bperche['’]?(?=\W|$)", "perché"),
    (r"\bPerche['’]?(?=\W|$)", "Perché"),
    (r"\bpoiche['’]?(?=\W|$)", "poiché"),
    (r"\bPoiche['’]?(?=\W|$)", "Poiché"),
    (r"\baffinche['’]?(?=\W|$)", "affinché"),
    (r"\bAffinche['’]?(?=\W|$)", "Affinché"),
    (r"\bgiacche['’]?(?=\W|$)", "giacché"),
    (r"\bGiacche['’]?(?=\W|$)", "Giacché"),
    (r"\bdopodiche['’]?(?=\W|$)", "dopodiché"),
    (r"\bDopodiche['’]?(?=\W|$)", "Dopodiché"),
    (r"\bnonche['’]?(?=\W|$)", "nonché"),
    (r"\bNonche['’]?(?=\W|$)", "Nonché"),
    (r"\bcioe['’]?(?=\W|$)", "cioè"),
    (r"\bCioe['’]?(?=\W|$)", "Cioè"),
    (r"\bcosi['’]?(?=\W|$)", "così"),
    (r"\bCosi['’]?(?=\W|$)", "Così"),
    (r"\bpuo['’]?(?=\W|$)", "può"),
    (r"\bPuo['’]?(?=\W|$)", "Può"),
    (r"\bpiu['’]?(?=\W|$)", "più"),
    (r"\bPiu['’]?(?=\W|$)", "Più"),
    (r"\bgia['’]?(?=\W|$)", "già"),
    (r"\bGia['’]?(?=\W|$)", "Già"),
    (r"\bpero['’]?(?=\W|$)", "però"),
    (r"\bPero['’]?(?=\W|$)", "Però"),
    (r"\bc['’]?[eè]['’]?(?=\W|$)", "c'è"),
    (r"\bC['’]?[eè]['’]?(?=\W|$)", "C'è"),
    (r"\bce['’]?\s+l[aà]\b", "ce l'ha"),
    (r"\bfa['’](?=\W|$)", "fa"),
    (r"\b[eE]['’](?=\W|$)", lambda m: "È" if m.group(0).startswith("E") else "è"),
]


# =========================================================================
# 4. NORMALIZZATORE PROSODICO INTEGRALE
# =========================================================================
class KeryxVerbalizer:
    """Motore di fonetica e prosodia vocale per ElevenLabs."""

    @classmethod
    def clean_markdown_and_code(cls, text: str) -> str:
        """Rimuove simboli visivi, blocchi di codice e percorsi senza alterare la semantica."""
        if not text:
            return ""

        t = text

        # 1. Rimpiazza blocchi di codice estesi ```...``` con locuzione parlata naturale
        t = re.sub(
            r"```[\w]*\s*\n?[\s\S]*?```",
            " Il blocco di codice relativo è evidenziato a schermo nel dossier tattico. ",
            t
        )

        # 2. Rimuove inline backticks `codice`
        t = re.sub(r"`([^`]+)`", r"\1", t)

        # 3. Rimuove intestazioni markdown (###, ##, #)
        t = re.sub(r"^[#=\-]{1,6}\s*", "", t, flags=re.MULTILINE)
        t = re.sub(r"\n[#=\-]{1,6}\s*", "\n", t)

        # 4. Rimuove grassetti e corsivi (**testo**, *testo*, _testo_)
        t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
        t = re.sub(r"\*([^*]+)\*", r"\1", t)
        t = re.sub(r"__([^_]+)__", r"\1", t)
        t = re.sub(r"_([^_]+)_", r"\1", t)

        # 5. Epurazione di percorsi file lunghi (C:\Users\...)
        t = re.sub(r"[A-Za-z]:\\[^\s\"']+", "nella cartella di progetto", t)
        t = re.sub(r"\b(?:[a-zA-Z_0-9\-]+/)+[a-zA-Z_0-9\-]+\.[a-zA-Z0-9]+\b", "nel file relativo", t)

        # 6. Semplifica estensioni file comuni
        t = re.sub(r"\.py\b", " file Python", t)
        t = re.sub(r"\.json\b", " file geison", t)
        t = re.sub(r"\.bat\b", " file batch", t)

        # 7. Converte elenchi numerati (1. , 2. ) in cadenza parlata
        t = re.sub(r"(?m)^\s*1\.\s+", "Punto primo: ", t)
        t = re.sub(r"(?m)^\s*2\.\s+", "Punto secondo: ", t)
        t = re.sub(r"(?m)^\s*3\.\s+", "Punto terzo: ", t)
        t = re.sub(r"(?m)^\s*4\.\s+", "Punto quarto: ", t)
        t = re.sub(r"(?m)^\s*5\.\s+", "Punto quinto: ", t)
        t = re.sub(r"(?m)^\s*\d+\.\s+", "Inoltre: ", t)

        # 8. Rimuove bullet point visivi (- , * )
        t = re.sub(r"(?m)^\s*[-*•]\s+", "Inoltre, ", t)

        # 9. Rimuove separatori orizzontali e tabelle
        t = re.sub(r"\|", " ", t)
        t = re.sub(r"[-=]{3,}", " ", t)

        return t

    @classmethod
    def repair_italian_accents(cls, text: str) -> str:
        """Ripristina accenti tonici e forme elise per una lettura vocale espressiva e corretta."""
        t = text
        for item in ACCENT_REPAIR_MAP:
            pattern = item[0]
            repl = item[1]
            t = re.sub(pattern, repl, t)
        return t

    @classmethod
    def verbalize_numbers_and_metrics(cls, text: str) -> str:
        """Converte numeri, percentuali, rapporti e anni in parole italiane esatte."""
        t = text

        # Rapporti tipo 15/15, 6/6, 8/15
        def repl_fraction(m):
            num1 = int_to_italian_words(int(m.group(1)))
            num2 = int_to_italian_words(int(m.group(2)))
            return f"{num1} su {num2}"
        t = re.sub(r"\b(\d+)\s*/\s*(\d+)\b", repl_fraction, t)

        # Percentuali tipo 100%, 85.5%
        def repl_pct(m):
            val_str = m.group(1).replace(",", ".")
            if "." in val_str:
                parts = val_str.split(".")
                interi = int_to_italian_words(int(parts[0]))
                dec = int_to_italian_words(int(parts[1][:2]))
                return f"{interi} virgola {dec} per cento"
            else:
                return f"{int_to_italian_words(int(val_str))} per cento"
        t = re.sub(r"\b(\d+(?:[.,]\d+)?)\s*%", repl_pct, t)

        # Millisecondi tipo 0.5ms, 12ms
        def repl_ms(m):
            num = m.group(1)
            if num == "0.5" or num == "0,5":
                return "mezzo millisecondo"
            return f"{cls.number_to_words(num)} millisecondi"
        t = re.sub(r"\b(\d+(?:[.,]\d+)?)\s*ms\b", repl_ms, t)

        # Kilobyte / Megabyte
        t = re.sub(r"\b(\d+)\s*KB\b", lambda m: f"{int_to_italian_words(int(m.group(1)))} kilobyte", t)
        t = re.sub(r"\b(\d+)\s*MB\b", lambda m: f"{int_to_italian_words(int(m.group(1)))} megabyte", t)

        # Numeri isolati (interi con virgole delle migliaia o normali)
        t = re.sub(r"\b(\d{1,3}(?:,\d{3})+)\b", lambda m: int_to_italian_words(int(m.group(1).replace(",", ""))), t)
        t = re.sub(r"\b(\d{1,7})\b", lambda m: int_to_italian_words(int(m.group(1))), t)

        return t

    @classmethod
    def apply_phonetic_dictionary(cls, text: str) -> str:
        """Applica la traslitterazione fonetica anglo-tecnica per la pronuncia impeccabile."""
        t = text
        for pattern, replacement in PHONETIC_TECH_MAP.items():
            t = re.sub(pattern, replacement, t)
        return t

    @classmethod
    def inject_breath_commas(cls, text: str) -> str:
        """
        Inietta pause di respiro prosodico davanti a congiunzioni forti e marcatori di discorso,
        garantendo un ritmo naturale ed espressivo come nella lettura di un libro.
        """
        t = text
        # Connettivi e congiunzioni avversative/consecutive che richiedono una pausa di respiro
        breath_markers = [
            "tuttavia", "pertanto", "infatti", "d'altronde", "per cui",
            "dopodiché", "benché", "sebbene", "poiché", "giacché",
            "ossia", "ovvero", "vale a dire", "di conseguenza"
        ]
        for marker in breath_markers:
            # Se preceduto da lettera/numero (senza virgola, punto o due punti), inserisce virgola prima
            pattern = rf"(?<=[a-zA-Z0-9àèéìòù])\s+\b({marker})\b"
            t = re.sub(pattern, r", \1", t, flags=re.IGNORECASE)

        # Marcatori all'inizio di frase o dopo punto/inizio riga che richiedono virgola dopo
        intro_markers = ["Inoltre", "In sintesi", "In conclusione", "Pertanto", "Tuttavia", "Infatti", "D'altronde"]
        for marker in intro_markers:
            pattern = rf"(^|[.?!]\s+)\b({marker})\b(?!\s*[,:])"
            t = re.sub(pattern, r"\1\2,", t)

        return t

    @classmethod
    def number_to_words(cls, num_str: str) -> str:
        """Helper per convertire stringa numerica in lettere."""
        clean = num_str.replace(",", ".").strip()
        try:
            if "." in clean:
                parts = clean.split(".")
                return f"{int_to_italian_words(int(parts[0]))} virgola {int_to_italian_words(int(parts[1]))}"
            return int_to_italian_words(int(clean))
        except Exception:
            return num_str

    @classmethod
    def polish_prosody_and_breathing(cls, text: str) -> str:
        """Pulisce la spaziatura e bilancia la punteggiatura espressiva (virgole, due punti, punti e virgola, punti)."""
        t = text
        # Se una riga finisce già con : ; . ! ? non aggiungere un punto che romperebbe la melodia prosodica
        lines = [line.strip() for line in t.split("\n") if line.strip()]
        reconstructed = []
        for line in lines:
            if line.endswith((":", ";", ".", "!", "?", ",")):
                reconstructed.append(line)
            else:
                reconstructed.append(line + ".")
        t = " ".join(reconstructed)

        # Pulizia spazi multipli
        t = re.sub(r"\s+", " ", t)

        # Rimuove doppie punteggiature incongruenti ma conserva i punti di sospensione (...)
        t = re.sub(r"\.{4,}", "...", t)
        t = re.sub(r",\s*,+", ",", t)
        t = re.sub(r"\.\s*,+", ".", t)
        t = re.sub(r",\s*\.+", ".", t)
        t = re.sub(r":\s*\.+", ":", t)
        t = re.sub(r";\s*\.+", ";", t)
        t = re.sub(r"\?\s*\.+", "?", t)
        t = re.sub(r"!\s*\.+", "!", t)
        t = re.sub(r"\s+([,.:;?!])", r"\1", t)

        return t.strip()

    @classmethod
    def format_speech_for_voice(cls, raw_text: str, max_chars: int = 3500) -> str:
        """
        Pipeline master di KERYX:
        Prende l'output raw dell'LLM e produce il testo fonetico perfetto per ElevenLabs.
        Supporta risposte analitiche estese fino a 3.500 caratteri.
        """
        if not raw_text or not raw_text.strip():
            return ""

        # 1. Rimozione sintassi visiva Markdown e blocchi codice
        clean = cls.clean_markdown_and_code(raw_text)

        # 2. Ripristino accenti tonici e forme elise (perché, può, più, cioè, così, già...)
        accented = cls.repair_italian_accents(clean)

        # 3. Conversione numerica integrale in parole italiane (2013 -> duemilatredici, 15/15 -> quindici su quindici)
        spoken = cls.verbalize_numbers_and_metrics(accented)

        # 4. Traslitterazione fonetica anglo-tecnica (API -> ei-pi-ai, Python -> Paiton...)
        phonetic = cls.apply_phonetic_dictionary(spoken)

        # 5. Iniezione pause di respiro prosodico (breath-pacing)
        with_breaths = cls.inject_breath_commas(phonetic)

        # 6. Bilanciamento punteggiatura espressiva (: ; , . ? !) e cadenza
        polished = cls.polish_prosody_and_breathing(with_breaths)

        # 7. Rispetto del limite massimo senza tagliare a metà frase
        if len(polished) <= max_chars:
            return polished

        # Se supera il tetto massimo (es. > 3500 caratteri), taglia su confine naturale di frase
        sub = polished[:max_chars]
        last_punct = max(sub.rfind("."), sub.rfind("!"), sub.rfind("?"), sub.rfind(":"))
        if last_punct > 500:
            return sub[:last_punct + 1].strip()

        last_space = sub.rfind(" ")
        return (sub[:last_space] if last_space > 500 else sub).strip() + "."


def verbalize_for_speech(raw_text: str, max_chars: int = 3500) -> str:
    """Funzione helper di convenienza per invocare KERYX."""
    return KeryxVerbalizer.format_speech_for_voice(raw_text, max_chars=max_chars)
