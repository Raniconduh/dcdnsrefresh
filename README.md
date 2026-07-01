# dcdnsrefresh

Refresh Discord CDN URLs automatically.

## Usage

dcdnsrefresh starts an HTTP server on port 8100. It takes a Discord CDN URL at
path `/cdn/{url}` where `url` is of one of the following forms:

* `https://cdn.discordapp.com/...`
* `cdn.discordapp.com/...`
* `/...`
* `.../...?ex=...&is=...&hm=...`

The client is then sent a 307 redirect with to the refreshed URL.

## Running

Install the requirements with `pip install -r requirements.txt`. Then run the
program as `python main.py`.
