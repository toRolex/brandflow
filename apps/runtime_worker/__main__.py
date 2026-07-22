from dotenv import load_dotenv

from apps.runtime_worker.loop import main


if __name__ == "__main__":
    load_dotenv()
    main()
