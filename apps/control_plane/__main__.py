import logging
import sys

from apps.control_plane.app import create_app
import uvicorn
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    uvicorn.run(create_app(), host="127.0.0.1", port=17890)


if __name__ == "__main__":
    main()
