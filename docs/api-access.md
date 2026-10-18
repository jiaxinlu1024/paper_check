# API keys and contact email

The skill's lookups need a contact email and two free API keys. Each person who runs the skill sets up their own. Everything goes in a user-level file, `~/.paper-check/config.yaml`, which never lives in a repository or next to a paper. On Windows the file is `%USERPROFILE%\.paper-check\config.yaml`.

```yaml
# ~/.paper-check/config.yaml. Never commit this file.
contact_email: you@your-institution.org
openalex_api_key: YOUR_OPENALEX_KEY
semantic_scholar_api_key: YOUR_SEMANTIC_SCHOLAR_KEY
repec_access_code: null
```

Use a real work or university address. Semantic Scholar does not issue keys to free email domains, and OpenAlex refuses placeholder addresses.

## Contact email

Crossref and Unpaywall need no key, only the contact email. With it, Crossref answers from its faster "polite" pool, and Unpaywall answers at all.

## OpenAlex key

There are two ways to get one. Both are free and give $1 of usage a day.

- **Let Claude request it.** OpenAlex lets an agent request a key for its user in one call, and `pc.py install --email ADDRESS --request-openalex-key` makes it: it sends your email address to `https://api.openalex.org/api-keys` and saves the key in your config file. OpenAlex emails you a message titled "Activate your OpenAlex API key". The key works once you click the button in that email. The link lasts 7 days.
- **Sign up on the website.** Make an account at https://openalex.org/signup, then copy your key from https://openalex.org/settings/api-key.

Single-paper lookups work without a key, but searches are throttled.

## Semantic Scholar key

Apply with the form at https://www.semanticscholar.org/product/api#api-key-form. The key arrives by email. A new key allows 1 request per second, and keys unused for about 60 days may be removed.

The form asks for:

| Field | What to enter |
|---|---|
| API Origin | S2 |
| First name, Last name, Email | Your own, with a work or university address |
| Affiliation and its website | Your employer or university |
| Country/Region | Yours |
| Application use | Private, for a tool used inside your team |
| How you plan to use the API, 50 words or more | See the sample below |
| Endpoints | `/paper/search/match`, `/paper/{paper_id}` with DOI or arXiv IDs, `/paper/batch`, `/paper/{paper_id}/citations`, `/paper/{paper_id}/references` |
| Requests per day | Up to about 2,000. A draft has 50 to 150 references |
| Four acknowledgements and the license | Read each one and tick it yourself. The skill does use exponential backoff |

Sample use description:

> We are building paper-check, an internal tool that reviews draft research papers in behavioral economics before submission. For each reference in a draft, it looks the paper up by DOI or by title to confirm that it exists and that its metadata is correct. It then retrieves the abstract and any open-access PDF, so it can check whether the cited paper supports the sentence that cites it. Citation contexts show how other papers describe the same work. Results are cached, and requests use exponential backoff.

## RePEc access

RePEc links economics working papers to their published versions. Its API is not open. You request access by email through the link on https://ideas.repec.org/api.html, which goes to team@mail.authors.repec.org. An approved user receives an access code that expires and can be renewed.

The request must state seven things:

1. Who you are.
2. The purpose of the API use.
3. Which data you need.
4. Why the standard method, harvesting RePEc's archives, is not used.
5. Which IP address will call the API.
6. The end date of the project.
7. The expected frequency of calls.

Template:

```text
Subject: RePEc API access request for paper-check

Dear Christian Zimmermann,

I would like to request access to the RePEc API.

1. Identity: [your name, role and organization, with your work email].
2. Purpose: paper-check, a tool that reviews draft economics papers before
   submission (https://github.com/jiaxinlu1024/paper_check). For each cited
   working paper, it checks whether a published version exists, so that
   authors cite the right version.
3. Data: references by RePEc handle (getref) and where working papers from a
   series were published (getpubsfromwpseries).
4. Why not the standard method: each draft needs only a few dozen small
   lookups on demand. Harvesting and maintaining a copy of the RePEc archives
   would be out of proportion for that.
5. IP address: [the public IP address the calls will come from].
6. End date: [for example 31 December 2027].
7. Frequency: at most about [200] calls a week, with results cached for
   7 days.

Thank you for considering this request.

[Your name]
```

To find your public IP address, ask your IT team for the office network's address, or run `curl https://ifconfig.me` on the laptop that will run the skill. Cloud sessions use shared addresses that change, so RePEc lookups should run from a laptop.

## Check the setup

```bash
python3 tools/check_network.py
```
