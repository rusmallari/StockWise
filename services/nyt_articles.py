
import os
import requests
from dotenv import load_dotenv

# Load the API key from .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

NYT_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"


def search_articles(query):
    # Get the API key
    api_key = os.getenv("NYT_API_KEY")

    if not api_key:
        return {"articles": [], "error": "NYT API key is missing."}

    if not query or not query.strip():
        return {"articles": [], "error": "Enter something to search."}

    # Send the search request to NYT
    params = {
        "api-key": api_key,
        "q": query.strip(),
        "sort": "relevance"
    }

    try:
        response = requests.get(NYT_URL, params=params, timeout=10)
    except requests.RequestException:
        return {"articles": [], "error": "Could not connect to NYT."}

    # Check for API errors
    if response.status_code in (401, 403):
        return {"articles": [], "error": "NYT API key was rejected."}

    if response.status_code == 429:
        return {"articles": [], "error": "Too many requests. Try again later."}

    if not response.ok:
        return {"articles": [], "error": "Could not load articles right now."}

    # Get the articles from the JSON response
    try:
        data = response.json()
        results = data.get("response", {}).get("docs", [])
    except (ValueError, AttributeError):
        return {"articles": [], "error": "Invalid response from NYT."}

    articles = []

    # Save the information we want to display
    for article in results:
        headline = article.get("headline") or {}

        articles.append({
            "title": headline.get("main") or "Untitled article",
            "summary": article.get("abstract") or article.get("snippet") or "",
            "url": article.get("web_url") or "",
            "date": (article.get("pub_date") or "")[:10],
            "section": article.get("section_name") or "News"
        })

    return {"articles": articles, "error": None}
