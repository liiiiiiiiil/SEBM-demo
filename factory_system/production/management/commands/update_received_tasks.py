"""
数据迁移命令：将状态为'received'的生产任务更新为'in_production'
"""
from django.core.management.base import BaseCommand
from production.models import ProductionTask


class Command(BaseCommand):
    help = '将状态为"已接收"的生产任务更新为"生产中"'

    def handle(self, *args, **options):
        tasks = ProductionTask.objects.filter(status='received')
        count = tasks.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('没有需要更新的任务'))
            return
        
        self.stdout.write(f'找到 {count} 个状态为"已接收"的任务，开始更新...')
        
        updated = 0
        for task in tasks:
            task.status = 'in_production'
            # 如果没有开始时间，设置为接收时间
            if not task.started_at and task.received_at:
                task.started_at = task.received_at
            task.save()
            updated += 1
            self.stdout.write(f'  已更新任务: {task.task_no}')
        
        self.stdout.write(self.style.SUCCESS(f'成功更新 {updated} 个任务的状态为"生产中"'))
