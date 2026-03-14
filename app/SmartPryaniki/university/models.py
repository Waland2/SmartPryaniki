from django.db import models


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