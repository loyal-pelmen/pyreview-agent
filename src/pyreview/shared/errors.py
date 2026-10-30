class AppError(Exception):
    status = 500
    code = "internal"
    default_message = "Внутренняя ошибка сервиса."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class UnsupportedFile(AppError):
    status = 400
    code = "unsupported_file"
    default_message = "Нужен один файл с расширением .py."


class FileTooLarge(AppError):
    status = 413
    code = "file_too_large"
    default_message = "Файл больше допустимого размера."


class NotUtf8(AppError):
    status = 422
    code = "not_utf8"
    default_message = "Файл не в кодировке UTF-8."


class ModelUnavailable(AppError):
    status = 502
    code = "model_unavailable"
    default_message = "Модель недоступна, попробуйте позже."


class AnalysisTimeout(AppError):
    status = 504
    code = "analysis_timeout"
    default_message = "Анализ не уложился в отведённое время."
