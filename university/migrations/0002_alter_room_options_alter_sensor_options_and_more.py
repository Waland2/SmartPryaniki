import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('university', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='room',
            options={'verbose_name': 'Кабинет', 'verbose_name_plural': 'Кабинеты'},
        ),
        migrations.AlterModelOptions(
            name='sensor',
            options={'verbose_name': 'Датчик', 'verbose_name_plural': 'Датчики'},
        ),
        migrations.AlterModelOptions(
            name='sensordata',
            options={'verbose_name': 'Показание датчика', 'verbose_name_plural': 'Показания датчиков'},
        ),
        migrations.AlterModelOptions(
            name='sensortype',
            options={'verbose_name': 'Тип датчика', 'verbose_name_plural': 'Типы датчиков'},
        ),
        migrations.AlterField(
            model_name='room',
            name='chairs',
            field=models.IntegerField(default=0, verbose_name='Количество стульев'),
        ),
        migrations.AlterField(
            model_name='room',
            name='computers',
            field=models.IntegerField(default=0, verbose_name='Количество компьютеров'),
        ),
        migrations.AlterField(
            model_name='room',
            name='conditioners',
            field=models.IntegerField(default=0, verbose_name='Количество кондиционеров'),
        ),
        migrations.AlterField(
            model_name='room',
            name='description',
            field=models.TextField(blank=True, verbose_name='Описание кабинета'),
        ),
        migrations.AlterField(
            model_name='room',
            name='desks',
            field=models.IntegerField(default=0, verbose_name='Количество парт'),
        ),
        migrations.AlterField(
            model_name='room',
            name='floor',
            field=models.IntegerField(verbose_name='Этаж'),
        ),
        migrations.AlterField(
            model_name='room',
            name='name',
            field=models.CharField(max_length=50, verbose_name='Название кабинета'),
        ),
        migrations.AlterField(
            model_name='room',
            name='windows',
            field=models.IntegerField(default=0, verbose_name='Количество окон'),
        ),
        migrations.AlterField(
            model_name='sensor',
            name='last_updated',
            field=models.DateTimeField(auto_now=True, verbose_name='Время последнего обновления'),
        ),
        migrations.AlterField(
            model_name='sensor',
            name='last_value',
            field=models.FloatField(blank=True, null=True, verbose_name='Последнее значение'),
        ),
        migrations.AlterField(
            model_name='sensor',
            name='name',
            field=models.CharField(max_length=100, verbose_name='Название датчика'),
        ),
        migrations.AlterField(
            model_name='sensor',
            name='room',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='university.room', verbose_name='Кабинет'),
        ),
        migrations.AlterField(
            model_name='sensor',
            name='sensor_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='university.sensortype', verbose_name='Тип датчика'),
        ),
        migrations.AlterField(
            model_name='sensor',
            name='status',
            field=models.CharField(choices=[('active', 'Работает'), ('error', 'Ошибка'), ('disabled', 'Выключен')], default='active', max_length=20, verbose_name='Статус'),
        ),
        migrations.AlterField(
            model_name='sensordata',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='Время записи'),
        ),
        migrations.AlterField(
            model_name='sensordata',
            name='sensor',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='university.sensor', verbose_name='Датчик'),
        ),
        migrations.AlterField(
            model_name='sensordata',
            name='value',
            field=models.FloatField(verbose_name='Значение'),
        ),
        migrations.AlterField(
            model_name='sensortype',
            name='name',
            field=models.CharField(max_length=100, verbose_name='Название типа датчика'),
        ),
    ]
