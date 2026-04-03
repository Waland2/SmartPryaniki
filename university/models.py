from django.db import models
from .simulators import get_simulator


class Room(models.Model):
    """
    Кабинет университета
    """

    name = models.CharField("Название кабинета", max_length=50)
    floor = models.IntegerField("Этаж")

    chairs = models.IntegerField("Количество стульев", default=0)
    desks = models.IntegerField("Количество парт", default=0)
    computers = models.IntegerField("Количество компьютеров", default=0)

    windows = models.IntegerField("Количество окон", default=0)
    conditioners = models.IntegerField("Количество кондиционеров", default=0)

    description = models.TextField("Описание кабинета", blank=True)

    def __str__(self):
        return self.name

    def simulate_sensors(self):
        return [sensor.read_from_simulator() for sensor in self.sensor_set.all()]

    class Meta:
        verbose_name = "Кабинет"
        verbose_name_plural = "Кабинеты"


class SensorType(models.Model):
    """
    Тип датчика
    """

    name = models.CharField("Название типа датчика", max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Тип датчика"
        verbose_name_plural = "Типы датчиков"


class Sensor(models.Model):
    """
    Датчик в кабинете
    """

    STATUS_CHOICES = [
        ("active", "Работает"),
        ("error", "Ошибка"),
        ("disabled", "Выключен"),
    ]

    room = models.ForeignKey(Room, verbose_name="Кабинет", on_delete=models.CASCADE)
    sensor_type = models.ForeignKey(SensorType, verbose_name="Тип датчика", on_delete=models.CASCADE)

    name = models.CharField("Название датчика", max_length=100)

    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default="active")

    last_value = models.FloatField("Последнее значение", null=True, blank=True)

    last_updated = models.DateTimeField("Время последнего обновления", auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.room})"

    @property
    def is_working(self):
        return self.status == 'active'

    def get_simulated_value(self):
        simulator = get_simulator(self)
        return simulator.generate_value()

    def read_from_simulator(self):
        if self.status != 'active':
            return {
                'sensor': self,
                'value': self.last_value,
                'saved': False,
                'message': 'Датчик неактивен',
            }

        value = self.get_simulated_value()
        self.last_value = value
        self.save(update_fields=['last_value', 'last_updated'])
        data = SensorData.objects.create(sensor=self, value=value)

        return {
            'sensor': self,
            'value': value,
            'saved': True,
            'message': 'Показание записано',
            'data': data,
        }

    class Meta:
        verbose_name = "Датчик"
        verbose_name_plural = "Датчики"


class SensorData(models.Model):
    """
    История значений датчиков
    """

    sensor = models.ForeignKey(Sensor, verbose_name="Датчик", on_delete=models.CASCADE)

    value = models.FloatField("Значение")

    created_at = models.DateTimeField("Время записи", auto_now_add=True)

    def __str__(self):
        return f"{self.sensor} : {self.value}"

    class Meta:
        verbose_name = "Показание датчика"
        verbose_name_plural = "Показания датчиков"
        ordering = ('-created_at',)

from django.conf import settings
from django.utils import timezone


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

    status = models.CharField("Статус", max_length=16, choices=STATUS_CHOICES, default="unread")
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
