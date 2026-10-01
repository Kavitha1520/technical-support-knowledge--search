from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, ArticleChunk
from app.services.rag import split_into_chunks

SAMPLE_ARTICLES = [
    {
        "title": "Fix ModuleNotFoundError for a Python package",
        "summary": "Install the missing package in the same Python environment that runs your application.",
        "category": "Programming",
        "technology": "Python",
        "product": "Python",
        "error_code": "ModuleNotFoundError",
        "difficulty": "Beginner",
        "tags": "python, pip, virtual environment, pandas, imports",
        "content": "Why it happens: Python cannot find the requested module in the interpreter's active environment.\n1. Check the interpreter used by your project: python -c \"import sys; print(sys.executable)\".\n2. Install the package with that interpreter: python -m pip install pandas.\n3. In VS Code, select the same environment with Python: Select Interpreter.\n4. If using a virtual environment, activate it before installing and running the application.\n5. Restart the Python process and verify with python -c \"import pandas; print(pandas.__version__)\".\nFor notebooks, select the kernel belonging to the environment where pandas is installed.",
    },
    {
        "title": "Connected to Wi-Fi but cannot reach the internet",
        "summary": "Check the network path, renew the device address, and compare with another device before resetting equipment.",
        "category": "Network",
        "technology": "Wi-Fi, DNS, DHCP",
        "product": "Windows, macOS, Linux",
        "error_code": "",
        "difficulty": "Beginner",
        "tags": "wifi, internet, dns, router, dhcp, connectivity",
        "content": "1. Check whether another device on the same Wi-Fi can browse. If none can, restart the router and modem, then wait two minutes.\n2. Turn Wi-Fi off and on, reconnect to the network, and check for a captive portal in a browser.\n3. Confirm the device received an IP address. On Windows run ipconfig; on macOS or Linux run ip addr.\n4. If an IP address exists, test a known address with ping 1.1.1.1, then test a hostname such as ping example.com.\n5. If the address test works but the hostname test fails, renew DNS settings or temporarily set DNS to 1.1.1.1 or 8.8.8.8 according to your organization's policy.\n6. Disable any VPN or proxy briefly to isolate the cause, then re-enable it. Contact your network administrator if the issue persists.",
    },
    {
        "title": "Resolve HTTP 500 errors in a web application",
        "summary": "Inspect application logs and reproduce the request before changing server configuration.",
        "category": "Software",
        "technology": "HTTP, web servers",
        "product": "Web application",
        "error_code": "HTTP 500",
        "difficulty": "Intermediate",
        "tags": "http, 500, server, logs, backend, api",
        "content": "1. Capture the request path, timestamp, and a request ID from the failing response.\n2. Inspect application logs for the matching timestamp and request ID; the response alone usually hides the underlying exception.\n3. Reproduce the request in a non-production environment with the same sanitized inputs.\n4. Check recent deployments, environment variables, database connectivity, and upstream service health.\n5. Fix the underlying exception and add a regression test. Do not expose stack traces or secrets in a public error response.\n6. If the issue began after a release and impact is high, follow your rollback procedure while investigating.",
    },
    {
        "title": "Troubleshoot database connection timeouts",
        "summary": "Verify network reachability, credentials, connection limits, and database health in that order.",
        "category": "Database",
        "technology": "PostgreSQL, SQL",
        "product": "PostgreSQL",
        "error_code": "connection timeout",
        "difficulty": "Intermediate",
        "tags": "database, postgres, timeout, connection pool, firewall",
        "content": "1. Confirm the database host and port are correct for the active environment.\n2. Test DNS resolution and network access from the application host; check firewall rules and VPN requirements.\n3. Verify credentials through the approved secret store without printing them to logs or command history.\n4. Check database health, active connections, and max_connections for saturation.\n5. Inspect application connection-pool settings for leaked or excessively long-lived connections.\n6. Retry with bounded timeouts and backoff. Avoid increasing connection limits until database capacity is understood.",
    },
    {
        "title": "Recover disk space safely on Windows",
        "summary": "Identify the largest folders first, then use built-in cleanup tools and avoid deleting system files manually.",
        "category": "Hardware",
        "technology": "Windows 11",
        "product": "Windows PC",
        "error_code": "Low disk space",
        "difficulty": "Beginner",
        "tags": "storage, disk, windows, cleanup, performance",
        "content": "1. Open Settings > System > Storage and review which categories use the most space.\n2. Empty Recycle Bin and remove temporary files through Storage settings or Disk Cleanup.\n3. Uninstall applications you recognize and no longer need from Settings > Apps.\n4. Move personal media to approved external or cloud storage after confirming it is backed up.\n5. Restart the computer and recheck free space.\nDo not manually delete files from Windows, Program Files, or unfamiliar application folders. Contact IT before cleaning a managed device.",
    },
    {
        "title": "Safely respond to a suspected phishing email",
        "summary": "Do not interact with the message; report it through your organization's approved channel.",
        "category": "Security",
        "technology": "Email security",
        "product": "Microsoft 365, Gmail",
        "error_code": "",
        "difficulty": "Beginner",
        "tags": "security, phishing, email, incident response",
        "content": "1. Do not click links, open attachments, reply, or forward the message normally.\n2. Use the Report phishing action in your mail client or your organization's security reporting process.\n3. If you entered credentials, change your password from a trusted device and notify your security team immediately.\n4. If you opened an attachment or installed software, disconnect from the network if instructed by policy and contact IT/security.\n5. Preserve the message for investigation; do not delete it unless your security team asks you to.",
    },
]


def seed_articles(db: Session) -> None:
    if db.scalar(select(Article.id).limit(1)) is not None:
        return
    for item in SAMPLE_ARTICLES:
        article = Article(**item)
        article.chunks.extend(
            ArticleChunk(chunk_index=index, content=content)
            for index, content in enumerate(split_into_chunks(f"{article.title}\n{article.summary}\n{article.content}"))
        )
        db.add(article)
    db.commit()
