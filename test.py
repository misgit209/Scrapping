import requests
from bs4 import BeautifulSoup

url = "https://www.gst.gov.in/"
response = requests.get(url)
soup = BeautifulSoup(response.text, "html.parser")

# Example 1: print all headings
for h2 in soup.find_all("h2"):
    print(h2.text.strip())

# Example 2: print all paragraphs
for p in soup.find_all("p"):
    print(p.text.strip())