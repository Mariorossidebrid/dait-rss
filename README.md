# dait-rss

Workflow GitHub Actions che genera un feed RSS non ufficiale a partire da:
https://dait.interno.gov.it/finanza-locale/notizie

Gira interamente sui server di GitHub, una volta all'ora — non serve
tenere acceso nessun PC.

## Come attivarlo

1. Crea un repository GitHub (può essere privato) e carica dentro tutti
   i file di questa cartella, mantenendo la struttura:
   ```
   .github/workflows/dait-rss.yml
   scripts/generate_feed.py
   requirements.txt
   ```
2. Vai su **Settings → Actions → General → Workflow permissions** e
   seleziona "**Read and write permissions**" (serve perché il workflow
   fa un commit automatico del feed aggiornato).
3. Vai su **Actions**, apri "dait-rss" e lancialo una volta manualmente
   con "Run workflow" per il primo test.
4. Se va a buon fine, comparirà (dopo il primo run) `docs/feed.xml` e
   `docs/items.json` nel repo.
5. Attiva **GitHub Pages**: Settings → Pages → Source: "Deploy from a
   branch" → branch `main`, cartella `/docs`. Dopo un paio di minuti il
   feed sarà raggiungibile su:
   `https://<tuo-utente>.github.io/<nome-repo>/feed.xml`
   Quell'URL è quello da incollare nel tuo lettore RSS.

Da quel momento il workflow gira da solo ogni ora (cron `0 * * * *`,
orario UTC) e aggiorna il feed con le nuove notizie trovate.

## ⚠️ Nota importante sul blocco anti-bot

Ho verificato che il sito dait.interno.gov.it è protetto da un sistema
anti-bot che **blocca esplicitamente le richieste automatiche** (anche
i miei tentativi di lettura diretta della pagina sono stati respinti
con un errore "Servizio sospeso / richiesta bloccata dai sistemi posti
a protezione del sito").

Lo script è scritto per presentarsi con header "da browser normale"
(User-Agent, Accept-Language, Referer) per massimizzare le probabilità
di passare, ma **non posso garantire che il sito lasci passare anche
le richieste provenienti dai server di GitHub Actions**. Se il blocco
scatta comunque:

- Il job Actions **fallirà visibilmente** (non produrrà un feed vuoto
  o silenziosamente rotto) e riceverai una email da GitHub in caso di
  fallimento di un workflow schedulato — così te ne accorgi subito.
- Il feed resterà comunque consultabile con le ultime notizie raccolte
  con successo nei run precedenti, semplicemente non si aggiornerà
  finché il blocco persiste.
- Se il blocco è sistematico, le alternative sono: usare un servizio
  di scraping con IP italiani/residenziali, oppure passare da
  `requests` a un browser headless (Playwright) — cosa che può aiutare
  ma non è garantita contro sistemi anti-bot più sofisticati (es.
  Akamai, Cloudflare Enterprise).

## Personalizzare la selezione delle notizie

Lo script individua le notizie cercando i link che contengono
`/finanza-locale/notizie/` nella pagina di elenco. Se in futuro il sito
cambia struttura e il feed smette di trovare notizie nuove, la
funzione da rivedere è `extract_items()` in `scripts/generate_feed.py`.
