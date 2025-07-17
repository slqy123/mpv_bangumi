import click
from bgm.dandanplay import main as dandanplay
from bgm.bangumi import main as bangumi


@click.group()
def main():
    pass


@main.command("open-url")
@click.argument("url")
def open_url(url: str):
    """Open a URL in the default web browser."""
    import webbrowser

    webbrowser.open(url)


main.add_command(dandanplay)
main.add_command(bangumi)

if __name__ == "__main__":
    main()
