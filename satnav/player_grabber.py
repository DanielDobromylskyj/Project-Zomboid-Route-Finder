import os
import platform

class PlayerCoords:
    def __init__(self):
        self.__path = self.get_path()
        self.__last = [0, 0, 0]


    def __find_path(self) -> str:
        platform_type = platform.system()

        if platform_type == "Windows":
            user_paths = [
                user
                for user in os.listdir(r"C:\Users")
                if user not in ("Public", "Default", "Default User", "WsiAccount", "desktop.ini", "All Users")
            ]

            if len(user_paths) > 1:
                for i, u in enumerate(user_paths):
                    print(f"[{i}] {u}")

                user = user_paths[int(input("Which [X] user are you?\n>"))]

            else:
                user = user_paths[0]

            return os.path.join(r"C:\Users", user, "Zomboid", "Lua")


        elif platform_type == "Linux":
            print(f"Windows Example: 'C:\\Users\\<Insert User Here>\\Zomboid\\Lua'")
            return input("Project Zomboid LUA/Mod output folder (called 'Lua')")

        elif platform_type == "Darwin":
            print("Mac User, Poor soul")
            return input("Project Zomboid LUA/Mod output folder (called 'Lua')")

        else:
            raise NotImplementedError("Unknown / Supported OS")

    def get_path(self):
        cache_dir = "data/cache"
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = f"{cache_dir}/coord_path.txt"

        if os.path.exists(cache_path):
            print("Fetch coord path from:", cache_path)
            with open(cache_path, "r") as f:
                return f.read()

        else:
            path = os.path.join(self.__find_path(), "player_coords.txt")

            with open(cache_path, "w") as f:
                f.write(path)

            return path

    def get_coords(self):
        try:
            with open(self.__path, "r") as f:
                data = f.read()

            self.__last = [
                float(axis)
                for axis in data.strip().split(",")
            ]
        except (OSError, ValueError) as e:
            pass

        return self.__last
