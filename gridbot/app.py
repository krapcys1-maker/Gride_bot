from gridbot.core.bot import GridBot


def main() -> None:
    bot = GridBot()
    try:
        bot.run()
    finally:
        bot.close()


if __name__ == "__main__":
    main()

