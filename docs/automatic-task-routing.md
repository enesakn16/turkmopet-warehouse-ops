# Otomatik görev yönlendirme

`warehouse-reconcile` komutu `--task-database` ile çalıştırıldığında yeni görevler artık sorumlu kuyruğa otomatik atanır.

## Yönlendirme kuralları

| Sorun türü | Atanan kuyruk |
|---|---|
| Mükerrer hareket veya eksik hareket kimliği | `integration-team` |
| SKU, miktar, stok, sayım farkı ve kritik stok sorunları | `warehouse-operations` |
| Eşleşmeyen yeni sorun kodları | `operations-supervisor` |

`QUARANTINED_MOVEMENT_ROW` kayıtlarında doğrulama nedeni ayrıca incelenir. `event_id`, `event id` veya `duplicate` içeren nedenler entegrasyon ekibine; diğer karantina nedenleri depo operasyonuna atanır.

## Güvenli tekrar çalıştırma

Otomatik yönlendirme yalnızca ilk kez oluşturulan görevlere uygulanır. Aynı sorun sonraki mutabakatlarda tekrar görülürse mevcut görev korunur. Elle değiştirilmiş atama, görev durumu ve çözüm geçmişi üzerine yazılmaz.

Görevleri kuyruk bazında görmek için:

```bash
warehouse-tasks --database warehouse.db list --assignee integration-team
warehouse-tasks --database warehouse.db list --assignee warehouse-operations
warehouse-tasks --database warehouse.db list --assignee operations-supervisor
```
