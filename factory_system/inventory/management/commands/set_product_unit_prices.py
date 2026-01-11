from django.core.management.base import BaseCommand
from inventory.models import Product
from decimal import Decimal


class Command(BaseCommand):
    help = '为所有成品设置合适的基础单价（基于售价的75%）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ratio',
            type=float,
            default=0.75,
            help='基础单价占售价的比例（默认0.75，即75%%）',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='强制更新已有单价的产品',
        )

    def handle(self, *args, **options):
        ratio = Decimal(str(options['ratio']))
        force = options['force']
        
        self.stdout.write('开始为成品设置基础单价...')
        
        products = Product.objects.all()
        updated_count = 0
        skipped_count = 0
        
        for product in products:
            # 如果产品已有单价且不强制更新，则跳过
            if product.unit_price and product.unit_price > 0 and not force:
                self.stdout.write(
                    self.style.WARNING(f'  跳过 {product.name} (已有单价: {product.unit_price}元)')
                )
                skipped_count += 1
                continue
            
            # 基于售价计算基础单价
            if product.sale_price and product.sale_price > 0:
                new_unit_price = product.sale_price * ratio
                product.unit_price = new_unit_price
                product.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  [OK] {product.name}: 售价{product.sale_price}元 -> 基础单价{new_unit_price:.2f}元'
                    )
                )
                updated_count += 1
            else:
                # 如果售价为0或未设置，设置一个默认的基础单价
                default_price = Decimal('100.00')  # 默认100元
                product.unit_price = default_price
                product.save()
                self.stdout.write(
                    self.style.WARNING(
                        f'  [WARN] {product.name}: 售价未设置，设置默认基础单价{default_price}元'
                    )
                )
                updated_count += 1
        
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'完成！共更新 {updated_count} 个产品，跳过 {skipped_count} 个产品'
            )
        )
