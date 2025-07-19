class VideoDoesNotExist(Exception):
    def __init__(self, video_path: str):
        super().__init__(
            f"Видео '{video_path}' не найдено. Проверьте правильность пути."
        )


class VideoMergingError(Exception):
    def __init__(self, error):
        super().__init__(f"Ошибка при объединении видео.\nПричина: {error}")


class VideoReadFrameError(Exception):
    def __init__(self, video_path: str):
        super().__init__(f"Не удалось прочитать кадр {1} из видео '{video_path}'.")
