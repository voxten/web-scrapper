from flask import Flask, jsonify, request, render_template, redirect, url_for
import os
import pymongo
import asyncio
import re
import requests
from bs4 import BeautifulSoup
from pymongo.server_api import ServerApi

# Flask app initialization
app = Flask(__name__)

# Fetching MongoDB connection details from environment variables
mongo_host = os.getenv('MONGO_HOST', 'localhost')
mongo_port = os.getenv('MONGO_PORT', '27017')
mongo_user = os.getenv('MONGO_INITDB_ROOT_USERNAME', 'root')
mongo_pass = os.getenv('MONGO_INITDB_ROOT_PASSWORD', 'pass')
mongo_url = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/"

client = pymongo.MongoClient(mongo_url, server_api=ServerApi('1'))

mydb = client["Projekt"]

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

# Helper function to convert ObjectId to string
def serialize_document(doc):
    if '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
async def scrape():
    url = request.form['url']
    html = await fetch_content(url)

    phone_number_patterns = [
        r'\b(?:\d{3} \d{3} \d{3}|\d{2} \d{3} \d{2} \d{2})\b',  # xxx xxx xxx or xx xxx xx xx
        r'\b\d{3}-\d{3}-\d{3}\b',  # xxx-xxx-xxx
        r'\b\d{3}.\d{3}.\d{3}\b',  # xxx.xxx.xxx
        r'\b\d{4} \d{3} \d{3}\b',  # xxxx xxx xxx
        r'\b\+\d{2} \d{3} \d{3} \d{3}\b',  # +xx xxx xxx xxx
        r'\b\+\d{2} \d{3}-\d{3}-\d{3}\b'  # +xx xxx-xxx-xxx
    ]

    tasks = [
        parse_phone_numbers(html, phone_number_patterns),
        parse_emails(html),
        parse_street_names(html),
        parse_cities(html)  # Parsing cities using city names file
    ]

    phone_numbers, emails, street_names, cities = await asyncio.gather(*tasks)

    results = {
        "phone_numbers": phone_numbers if phone_numbers else [],
        "emails": emails if emails else [],
        "street_names": street_names if street_names else [],
        "cities": cities if cities else []
    }

    # Create a new collection for the site
    site_collection = mydb[url.replace("https://", "").replace("/", "_")]

    # Store scraped data in MongoDB with site information
    if phone_numbers:
        site_collection.insert_one({"type": "phone_numbers", "data": phone_numbers})

    if emails:
        site_collection.insert_one({"type": "emails", "data": emails})

    if street_names:
        site_collection.insert_one({"type": "street_names", "data": street_names})

    if cities:
        site_collection.insert_one({"type": "cities", "data": cities})

    return render_template('results.html', url=url, results=results)

@app.route('/all_data')
def all_data():
    collections = mydb.list_collection_names()
    all_data = {}
    for collection_name in collections:
        collection = mydb[collection_name]
        documents = collection.find()
        all_data[collection_name] = [serialize_document(doc) for doc in documents]

    return render_template('all_data.html', all_data=all_data)

@app.route('/delete_all', methods=['POST'])
def delete_all():
    collections = mydb.list_collection_names()
    for collection_name in collections:
        mydb[collection_name].drop()  # Drop the collection
    return redirect(url_for('all_data'))

# Asynchronous functions for scraping and parsing
async def fetch_content(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        return None

async def parse_phone_numbers(html, patterns):
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        phone_numbers = []
        for pattern in patterns:
            phone_numbers.extend(re.findall(pattern, soup.get_text()))
        return list(set(phone_numbers))
    else:
        return None

async def parse_emails(html):
    if html:
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', html)
        return list(set(emails))
    else:
        return None

async def parse_street_names(html):
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        street_names = [tag.get_text() for tag in soup.find_all(string=re.compile(r'^ul\.', re.IGNORECASE))]
        return list(set(street_names))
    else:
        return None

async def parse_cities(html):
    city_file = 'city_names.txt'
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        try:
            with open(city_file, 'r') as f:
                city_names = [line.strip() for line in f]
        except FileNotFoundError:
            print("City file not found.")
            return None

        cities = []
        for city_name in city_names:
            city_matches = soup.find_all(string=re.compile(r'\b{}\b'.format(re.escape(city_name)), re.IGNORECASE))
            if city_matches:
                cities.extend(city_matches)
        return list(set(cities))  # Remove duplicates
    else:
        return None

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
