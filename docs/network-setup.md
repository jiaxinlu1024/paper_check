# Network access for paper-check

The skill looks up every reference in scholarly databases. It also fetches the text of cited papers to test whether they support the claims made about them. Both need internet access to the services listed in `tools/check_network.py`. Without access, the skill reports those checks as skipped, never as passed.

## Where this applies

- **Claude Code desktop on a laptop.** Usually nothing to do, because the laptop's own network is used. A university or company firewall or VPN can still block some hosts, so run the check script once.
- **Cloud sessions,** at claude.ai/code or with Cloud selected in the desktop app. The cloud environment's network access level controls outbound traffic. The default level, Trusted, blocks every scholarly host.

Cloud environments are personal. Your coworker's cloud environment has its own setting. On Team and Enterprise plans, an Owner can create an organization-shared environment with one standard list.

## Option A: Full access, for the best results

1. In a running session, select the caret after the session title at the top, then select **Edit cloud environment**. For a new session, open the environment selector under the message box, hover over the environment, and select its settings icon.
2. Set **Network access** to **Full**.
3. Save. Running sessions pick up the new setting within about a minute.

Fact checks and full-text retrieval need sites that no list can anticipate. Examples are authors' homepages that host working papers, statistical agencies and news sources.

The trade-off is that any website becomes reachable. A malicious page could try to instruct Claude to send data elsewhere. The skill treats every fetched page as data, never as instructions. This is the same exposure as running Claude Code on a laptop.

## Option B: Custom list, for tighter control

1. Open the same dialog and set **Network access** to **Custom**.
2. Paste the contents of `config/allowed-domains.txt` into **Allowed domains**.
3. Tick **Also include default list of common package managers**, so Python packages still install.
4. Save.

With this option the skill cannot open pages outside the list, such as authors' homepages, statistical agencies and news sites. Fact checks then rely on search results alone. You can add domains at any time. A line starting with `*.` matches every subdomain, but not the bare domain itself.

## Check the result

```bash
python3 tools/check_network.py
```

Every required host should show OK. Some publishers and SSRN use bot protection and may answer with HTTP 403. The script counts that as reachable, because the network path is open, but the skill may not be able to read pages there. In that case it falls back to other sources and says so in the report.

Official documentation: https://code.claude.com/docs/en/cloud-environments#network-access
