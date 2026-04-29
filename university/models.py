from django.conf import settings
from django.db import models
from django.utils import timezone

from .simulators import get_simulator


class Room(models.Model):
    name = models.CharField("Название кабинета", max_length=50)
    floor = models.IntegerField("Этаж")

    chairs = models.IntegerField("Количество стульев", default=0)
    desks = models.IntegerField("Количество парт", default=0)
    computers = models.IntegerField("Количество компьютеров", default=0)

    windows = models.IntegerField("Количество окон", default=0)
    description = models.TextField("Описание кабинета", blank=True)
    window_open = models.BooleanField("Окна открыты", default=False)

    conditioners = models.IntegerField("Количество кондиционеров", default=0)

    def __str__(self):
        return self.name

    def simulate_sensors(self):
        return [sensor.read_from_simulator() for sensor in self.sensor_set.all()]

    def get_active_conditioners(self):
        return self.conditioner_set.filter(status="active", enabled=True)

    def get_cooling_conditioners(self):
        return self.get_active_conditioners().filter(mode="cool")

    def get_heating_conditioners(self):
        return self.get_active_conditioners().filter(mode="heat")

    def get_total_cooling_power(self):
        return sum(item.power for item in self.get_cooling_conditioners())

    def get_total_heating_power(self):
        return sum(item.power for item in self.get_heating_conditioners())

    class Meta:
        verbose_name = "Кабинет"
        verbose_name_plural = "Кабинеты"


class ClimateActionLog(models.Model):
    ACTION_CHOICES = [
        ("ventilation", "Проветривание"),
        ("conditioner_cool", "Кондиционер: охлаждение"),
        ("conditioner_heat", "Кондиционер: обогрев"),
        ("none", "Без вмешательства"),
    ]

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        verbose_name="Кабинет",
        related_name="climate_logs",
    )

    lesson_date = models.DateField("Дата занятия")
    lesson_time = models.TimeField("Время начала занятия")

    action = models.CharField(
        "Выполненное действие",
        max_length=50,
        choices=ACTION_CHOICES,
    )

    reason = models.TextField("Причина выбора действия", blank=True)
    created_at = models.DateTimeField("Время выполнения", auto_now_add=True)

    class Meta:
        verbose_name = "История настройки кабинета"
        verbose_name_plural = "История настройки кабинетов"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.room} — {self.get_action_display()} — {self.created_at:%d.%m.%Y %H:%M}"


class Conditioner(models.Model):
    STATUS_CHOICES = [
        ("active", "Работает"),
        ("error", "Ошибка"),
        ("disabled", "Выключен"),
    ]

    MODE_CHOICES = [
        ("off", "Выключен"),
        ("cool", "Охлаждение"),
        ("heat", "Обогрев"),
        ("fan", "Вентиляция"),
    ]

    room = models.ForeignKey(
        Room,
        verbose_name="Кабинет",
        on_delete=models.CASCADE,
    )

    name = models.CharField("Название кондиционера", max_length=100)

    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    enabled = models.BooleanField("Включен", default=False)

    mode = models.CharField(
        "Режим",
        max_length=10,
        choices=MODE_CHOICES,
        default="off",
    )

    target_temperature = models.FloatField(
        "Целевая температура",
        null=True,
        blank=True,
    )

    power = models.FloatField("Мощность", default=1.0)
    last_updated = models.DateTimeField("Время последнего обновления", auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.room})"

    class Meta:
        verbose_name = "Кондиционер"
        verbose_name_plural = "Кондиционеры"


class SensorType(models.Model):
    name = models.CharField("Название типа датчика", max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Тип датчика"
        verbose_name_plural = "Типы датчиков"


class Sensor(models.Model):
    STATUS_CHOICES = [
        ("active", "Работает"),
        ("error", "Ошибка"),
        ("disabled", "Выключен"),
    ]

    room = models.ForeignKey(
        Room,
        verbose_name="Кабинет",
        on_delete=models.CASCADE,
    )

    sensor_type = models.ForeignKey(
        SensorType,
        verbose_name="Тип датчика",
        on_delete=models.CASCADE,
    )

    name = models.CharField("Название датчика", max_length=100)

    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    last_value = models.FloatField("Последнее значение", null=True, blank=True)
    last_updated = models.DateTimeField("Время последнего обновления", auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.room})"

    @property
    def is_working(self):
        return self.status == "active"

    def get_simulated_value(self):
        simulator = get_simulator(self)
        return simulator.generate_value()

    def read_from_simulator(self):
        if self.status != "active":
            return {
                "sensor": self,
                "value": self.last_value,
                "saved": False,
                "message": "Датчик неактивен",
            }

        value = self.get_simulated_value()
        self.last_value = value
        self.save(update_fields=["last_value", "last_updated"])

        data = SensorData.objects.create(sensor=self, value=value)

        return {
            "sensor": self,
            "value": value,
            "saved": True,
            "message": "Показание записано",
            "data": data,
        }

    class Meta:
        verbose_name = "Датчик"
        verbose_name_plural = "Датчики"


class SensorData(models.Model):
    sensor = models.ForeignKey(
        Sensor,
        verbose_name="Датчик",
        on_delete=models.CASCADE,
    )

    value = models.FloatField("Значение")
    created_at = models.DateTimeField("Время записи", auto_now_add=True)

    def __str__(self):
        return f"{self.sensor}: {self.value}"

    class Meta:
        verbose_name = "Показание датчика"
        verbose_name_plural = "Показания датчиков"
        ordering = ("-created_at",)


class TeacherNotification(models.Model):
    TYPE_CHOICES = [
        ("environment_setup", "Настройка среды"),
        ("preparation", "Подготовка кабинета"),
    ]

    STATUS_CHOICES = [
        ("unread", "Не прочитано"),
        ("read", "Прочитано"),
        ("dismissed", "Скрыто"),
    ]

    ACTION_CHOICES = [
        ("pending", "Не выбрано"),
        ("manual", "Настрою сам"),
        ("algorithm", "Оставить алгоритму"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_notifications",
        verbose_name="Пользователь",
    )

    notification_type = models.CharField(
        "Тип уведомления",
        max_length=32,
        choices=TYPE_CHOICES,
        default="environment_setup",
    )

    title = models.CharField("Заголовок", max_length=255)
    message = models.TextField("Сообщение")

    lesson_date = models.DateField("Дата занятия")
    lesson_number = models.CharField("Номер пары", max_length=8, blank=True)
    room_name = models.CharField("Кабинет", max_length=64, blank=True)
    subject_name = models.CharField("Предмет", max_length=255, blank=True)
    group_name = models.CharField("Группа", max_length=64, blank=True)

    recommended_temperature = models.DecimalField(
        "Рекомендуемая температура",
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    temperature_min = models.DecimalField(
        "Минимальная температура",
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    temperature_max = models.DecimalField(
        "Максимальная температура",
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    action_choice = models.CharField(
        "Выбор преподавателя",
        max_length=16,
        choices=ACTION_CHOICES,
        default="pending",
    )

    payload = models.JSONField("Дополнительные данные", default=dict, blank=True)

    status = models.CharField(
        "Статус",
        max_length=16,
        choices=STATUS_CHOICES,
        default="unread",
    )

    show_popup = models.BooleanField("Показывать popup", default=True)

    valid_from = models.DateTimeField("Показывать с")
    valid_until = models.DateTimeField("Показывать до")

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    read_at = models.DateTimeField("Прочитано", null=True, blank=True)
    action_at = models.DateTimeField("Выбор сделан", null=True, blank=True)

    class Meta:
        verbose_name = "Уведомление преподавателя"
        verbose_name_plural = "Уведомления преподавателей"
        ordering = ["-valid_from", "-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["lesson_date", "lesson_number"]),
            models.Index(fields=["valid_from", "valid_until"]),
        ]

    def __str__(self):
        return f"{self.user} · {self.title}"

    @property
    def is_actual(self):
        now = timezone.now()
        return self.valid_from <= now <= self.valid_until


class RoomLesson(models.Model):
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="lessons",
        verbose_name="Кабинет",
    )

    lesson_date = models.DateField("Дата занятия")
    pair_number = models.IntegerField("Номер пары", null=True, blank=True)

    start_time = models.TimeField("Время начала")
    end_time = models.TimeField("Время окончания")

    subject = models.CharField("Предмет", max_length=255, blank=True)
    teacher = models.CharField("Преподаватель", max_length=255, blank=True)
    group_name = models.CharField("Группа", max_length=100, blank=True)

    external_id = models.CharField(
        "ID записи во внешнем источнике",
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
    )

    source = models.CharField("Источник", max_length=50, default="import")
    is_cancelled = models.BooleanField("Отменено", default=False)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Занятие кабинета"
        verbose_name_plural = "Занятия кабинетов"
        ordering = ("lesson_date", "start_time")
        indexes = [
            models.Index(fields=["room", "lesson_date", "start_time"]),
            models.Index(fields=["lesson_date", "is_cancelled"]),
        ]

    def __str__(self):
        return f"{self.room.name} | {self.lesson_date} | {self.start_time}"