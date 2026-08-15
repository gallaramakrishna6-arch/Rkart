# RKart

RKart is an AI-powered price comparison platform that collects product information from multiple e-commerce websites and displays it in one place — helping users compare prices, offers, and product details to make smarter purchasing decisions.

🔗 **Live Demo:** [rkart-production.up.railway.app](https://rkart-production.up.railway.app)

## Screenshots

| Home | Home (Categories) |
|---|---|
| ![Home](screenshots/rkart%20home1.jpg) | ![Home Categories](screenshots/rkart%20home2.jpg) |

| Electronics | Pricing / Search Results |
|---|---|
| ![Electronics](screenshots/rkart%20electronics1.jpg) | ![Price](screenshots/rkart%20price.jpg) |

## Supported Stores
- Amazon
- Flipkart
- Croma
- Reliance Digital
- Myntra
- JioMart
- BigBasket

## Features
- **Multi-site search** — search once, get ranked results from multiple stores
- **Category browsing** — Electronics, Electronics Accessories, Clothes, Grocery — each routed to the right stores only
- **Smart filtering** — strict subcategory rules avoid irrelevant results (e.g. searching "HP laptop" won't show laptop bags)
- **Compare List** — add products from different stores and compare side by side
- **Collections** — organize saved products into custom folders
- **Saved Products** — a flat favorites list for quick access
- **Recently Compared** — see your search history at a glance
- **Best Prices Today** — homepage snapshot of the cheapest real results found recently
- **URL Analyzer** — paste a product link and RKart guesses the product name and searches for it across stores
- **User accounts** — signup/login to save your data

## Tech Stack
- **Backend:** Python, Flask
- **Scraping:** Selenium (headless Chrome)
- **Database:** SQLite
- **Translation:** deep-translator (Google Translate)
- **Deployment:** Docker, Railway

## Running Locally

```bash
pip install -r requirements.txt
python app.py
```

Create a `.env` file in the project root with:
```
SECRET_KEY=<a long random string>
```

Generate one with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Deployment

This project includes a `Dockerfile` for containerized deployment (tested on Railway). Set the `SECRET_KEY` environment variable on your platform before deploying.
