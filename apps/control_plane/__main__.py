from apps.control_plane.app import create_app
import uvicorn


def main() -> None:
    uvicorn.run(create_app(), host="127.0.0.1", port=17890)


if __name__ == "__main__":
    main()
