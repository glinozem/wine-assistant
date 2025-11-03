"""
Unit tests for scripts/idempotency.py

Цель: Покрытие 80%+ для модуля идемпотентности ETL.
Issue: #91

Coverage target: 25.00% → 80%+
"""
import os
import pytest
import hashlib
from datetime import date, datetime
from uuid import UUID
import psycopg2.extras
from scripts.idempotency import (
    compute_file_sha256,
    check_file_exists,
    create_envelope,
    update_envelope_status,
    create_price_list_entry
)


# =============================================================================
# Tests for compute_file_sha256()
# =============================================================================

@pytest.mark.unit
class TestComputeFileSHA256:
    """Тесты для функции compute_file_sha256()"""

    def test_compute_sha256_returns_64_char_hex(self, tmp_path):
        """
        Test: SHA256 hash должен быть 64 hex-символа.

        Arrange: Создать временный файл
        Act: Вычислить SHA256
        Assert: Длина хеша 64 символа, только hex
        """
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, Wine Assistant!")

        # Act
        result = compute_file_sha256(str(test_file))

        # Assert
        assert len(result) == 64, "SHA256 hash должен быть 64 символа"
        assert all(c in '0123456789abcdef' for c in result), \
            "SHA256 hash должен содержать только hex символы"

    def test_compute_sha256_same_content_same_hash(self, tmp_path):
        """
        Test: Одинаковый контент → одинаковый хеш.

        Arrange: Создать два файла с одинаковым контентом
        Act: Вычислить хеши обоих файлов
        Assert: Хеши идентичны
        """
        # Arrange
        content = "Price list content for Wine Assistant"
        file1 = tmp_path / "file1.xlsx"
        file2 = tmp_path / "file2.xlsx"
        file1.write_text(content, encoding='utf-8')
        file2.write_text(content, encoding='utf-8')

        # Act
        hash1 = compute_file_sha256(str(file1))
        hash2 = compute_file_sha256(str(file2))

        # Assert
        assert hash1 == hash2, \
            "Одинаковый контент должен давать одинаковый SHA256 hash"

    def test_compute_sha256_different_content_different_hash(self, tmp_path):
        """
        Test: Разный контент → разные хеши.

        Arrange: Создать два файла с разным контентом
        Act: Вычислить хеши
        Assert: Хеши различаются
        """
        # Arrange
        file1 = tmp_path / "prices_v1.xlsx"
        file2 = tmp_path / "prices_v2.xlsx"
        file1.write_text("Version 1 prices: 100 RUB", encoding='utf-8')
        file2.write_text("Version 2 prices: 200 RUB", encoding='utf-8')

        # Act
        hash1 = compute_file_sha256(str(file1))
        hash2 = compute_file_sha256(str(file2))

        # Assert
        assert hash1 != hash2, \
            "Разный контент должен давать разные SHA256 hashes"

    def test_compute_sha256_handles_large_files(self, tmp_path):
        """
        Test: SHA256 корректно обрабатывает большие файлы (>8KB chunks).

        Arrange: Создать файл >8KB (размер chunk)
        Act: Вычислить SHA256
        Assert: Хеш вычислен корректно
        """
        # Arrange
        large_file = tmp_path / "large_file.txt"
        # Создать файл размером ~10KB (больше чем 8KB chunk)
        content = "A" * 10240  # 10KB данных
        large_file.write_text(content, encoding='utf-8')

        # Act
        result = compute_file_sha256(str(large_file))

        # Assert
        assert len(result) == 64
        # Проверить что хеш соответствует ожидаемому (вычислить эталонный)
        expected_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        assert result == expected_hash, \
            "SHA256 для большого файла должен быть вычислен корректно"


# =============================================================================
# Tests for check_file_exists()
# =============================================================================

@pytest.mark.unit
class TestCheckFileExists:
    """Тесты для функции check_file_exists()"""

    def test_check_file_exists_returns_none_for_new_hash(self, db_connection):
        """
        Test: Новый хеш → функция возвращает None.

        Arrange: Сгенерировать несуществующий хеш
        Act: Проверить наличие в БД
        Assert: Результат None
        """
        # Arrange
        fake_hash = "a" * 64  # Несуществующий хеш

        # Act
        result = check_file_exists(db_connection, fake_hash)

        # Assert
        assert result is None, \
            "check_file_exists должен возвращать None для несуществующего хеша"

    def test_check_file_exists_returns_dict_for_existing_hash(self,
                                                              db_connection):
        """
        Test: Существующий хеш → функция возвращает dict.

        Arrange: Создать envelope с известным хешем
        Act: Проверить наличие
        Assert: Результат содержит envelope_id и file_sha256
        """
        # Arrange
        test_hash = "b" * 64
        test_file_name = "test_prices.xlsx"

        # Создать тестовый envelope
        cursor = db_connection.cursor()
        cursor.execute("""
                       INSERT INTO ingest_envelope (file_name, file_sha256, status)
                       VALUES (%s, %s, 'success') RETURNING envelope_id
                       """, (test_file_name, test_hash))
        envelope_id = cursor.fetchone()[0]
        db_connection.commit()

        try:
            # Act
            result = check_file_exists(db_connection, test_hash)

            # Assert
            assert result is not None, \
                "check_file_exists должен возвращать dict для существующего хеша"
            assert result['file_sha256'] == test_hash
            assert result['envelope_id'] == envelope_id
            assert result['file_name'] == test_file_name
            assert result['status'] == 'success'

        finally:
            # Cleanup
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,))
            db_connection.commit()
            cursor.close()

    def test_check_file_exists_returns_all_required_fields(self,
                                                           db_connection):
        """
        Test: check_file_exists возвращает все необходимые поля.

        Arrange: Создать полностью заполненный envelope
        Act: Проверить наличие
        Assert: Все поля присутствуют в результате
        """
        # Arrange
        test_hash = "c" * 64
        cursor = db_connection.cursor()
        cursor.execute("""
                       INSERT INTO ingest_envelope
                       (file_name, file_sha256, status, rows_inserted,
                        rows_updated, rows_failed)
                       VALUES (%s, %s, 'success', 100, 50,
                               5) RETURNING envelope_id
                       """, ("full_test.xlsx", test_hash))
        envelope_id = cursor.fetchone()[0]
        db_connection.commit()

        try:
            # Act
            result = check_file_exists(db_connection, test_hash)

            # Assert
            required_fields = [
                'envelope_id', 'file_name', 'file_sha256',
                'upload_timestamp', 'status', 'rows_inserted',
                'rows_updated', 'rows_failed'
            ]
            for field in required_fields:
                assert field in result, f"Поле {field} должно присутствовать в результате"

            assert result['rows_inserted'] == 100
            assert result['rows_updated'] == 50
            assert result['rows_failed'] == 5

        finally:
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,))
            db_connection.commit()
            cursor.close()


# =============================================================================
# Tests for create_envelope()
# =============================================================================

@pytest.mark.unit
class TestCreateEnvelope:
    """Тесты для функции create_envelope()"""

    def test_create_envelope_inserts_and_returns_uuid(self, db_connection):
        """
        Test: Создание envelope возвращает UUID.

        Arrange: Подготовить данные для envelope
        Act: Создать envelope
        Assert: Возвращён UUID, запись в БД существует
        """
        # Arrange
        file_hash = "d" * 64
        file_name = "test_prices_create.xlsx"

        try:
            # Act
            envelope_id = create_envelope(
                db_connection,
                file_name=file_name,
                file_hash=file_hash,
                file_path="/inbox/test.xlsx",
                file_size_bytes=1024
            )

            # Assert
            assert envelope_id is not None, "envelope_id не должен быть None"
            # psycopg2 возвращает UUID как строку, не как объект UUID
            assert isinstance(envelope_id, (UUID,
                                            str)), "envelope_id должен быть UUID или строка UUID"
            # Проверить формат UUID (36 символов с дефисами)
            uuid_str = str(envelope_id)
            assert len(
                uuid_str) == 36, "UUID должен быть 36 символов с дефисами"
            # Проверить что это валидный UUID (можно распарсить)
            try:
                UUID(uuid_str)
            except ValueError:
                pytest.fail(
                    f"envelope_id не является валидным UUID: {uuid_str}")

            # Проверить что запись создана в БД
            cursor = db_connection.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "SELECT * FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,)
            )
            record = cursor.fetchone()
            cursor.close()

            assert record is not None, "Запись должна существовать в БД"
            assert record['file_sha256'] == file_hash
            assert record['file_name'] == file_name
            assert record['status'] == 'processing'
            assert record['file_path'] == "/inbox/test.xlsx"
            assert record['file_size_bytes'] == 1024

        finally:
            # Cleanup
            cursor = db_connection.cursor()
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE file_sha256 = %s",
                (file_hash,))
            db_connection.commit()
            cursor.close()

    def test_create_envelope_sets_default_status_processing(self,
                                                            db_connection):
        """
        Test: По умолчанию envelope создаётся со статусом 'processing'.

        Arrange: Подготовить минимальные данные
        Act: Создать envelope
        Assert: Статус = 'processing'
        """
        # Arrange
        file_hash = "e" * 64
        file_name = "status_test.xlsx"

        try:
            # Act
            envelope_id = create_envelope(
                db_connection,
                file_name=file_name,
                file_hash=file_hash
            )

            # Assert
            cursor = db_connection.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "SELECT status FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,)
            )
            status = cursor.fetchone()['status']
            cursor.close()

            assert status == 'processing', \
                "Статус по умолчанию должен быть 'processing'"

        finally:
            cursor = db_connection.cursor()
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE file_sha256 = %s",
                (file_hash,))
            db_connection.commit()
            cursor.close()


# =============================================================================
# Tests for update_envelope_status()
# =============================================================================

@pytest.mark.unit
class TestUpdateEnvelopeStatus:
    """Тесты для функции update_envelope_status()"""

    def test_update_envelope_status_success(self, db_connection):
        """
        Test: Обновление статуса envelope на 'success' работает корректно.

        Arrange: Создать envelope со статусом 'processing'
        Act: Обновить статус на 'success'
        Assert: Статус изменён, счётчики обновлены
        """
        # Arrange
        file_hash = "f" * 64
        envelope_id = create_envelope(
            db_connection,
            file_name="update_test.xlsx",
            file_hash=file_hash
        )

        try:
            # Act
            update_envelope_status(
                db_connection,
                envelope_id=envelope_id,
                status='success',
                rows_inserted=100,
                rows_updated=50,
                rows_failed=0
            )

            # Assert
            cursor = db_connection.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                           SELECT status,
                                  rows_inserted,
                                  rows_updated,
                                  rows_failed,
                                  processing_completed_at
                           FROM ingest_envelope
                           WHERE envelope_id = %s
                           """, (envelope_id,))
            record = cursor.fetchone()
            cursor.close()

            assert record['status'] == 'success'
            assert record['rows_inserted'] == 100
            assert record['rows_updated'] == 50
            assert record['rows_failed'] == 0
            assert record['processing_completed_at'] is not None, \
                "processing_completed_at должен быть установлен"

        finally:
            cursor = db_connection.cursor()
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,))
            db_connection.commit()
            cursor.close()

    def test_update_envelope_status_failed_with_error_message(self,
                                                              db_connection):
        """
        Test: Обновление статуса на 'failed' с сообщением об ошибке.

        Arrange: Создать envelope
        Act: Обновить статус на 'failed' с error_message
        Assert: Статус и error_message обновлены
        """
        # Arrange
        file_hash = "0" * 64
        envelope_id = create_envelope(
            db_connection,
            file_name="failed_test.xlsx",
            file_hash=file_hash
        )
        error_msg = "Test error: File parsing failed"

        try:
            # Act
            update_envelope_status(
                db_connection,
                envelope_id=envelope_id,
                status='failed',
                rows_failed=10,
                error_message=error_msg
            )

            # Assert
            cursor = db_connection.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                           SELECT status, error_message, rows_failed
                           FROM ingest_envelope
                           WHERE envelope_id = %s
                           """, (envelope_id,))
            record = cursor.fetchone()
            cursor.close()

            assert record['status'] == 'failed'
            assert record['error_message'] == error_msg
            assert record['rows_failed'] == 10

        finally:
            cursor = db_connection.cursor()
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,))
            db_connection.commit()
            cursor.close()


# =============================================================================
# Tests for create_price_list_entry()
# =============================================================================

@pytest.mark.unit
class TestCreatePriceListEntry:
    """Тесты для функции create_price_list_entry()"""

    def test_create_price_list_entry_links_to_envelope(self, db_connection):
        """
        Test: Создание price_list записи связывает с envelope.

        Arrange: Создать envelope
        Act: Создать price_list запись
        Assert: Связь установлена, запись создана
        """
        # Arrange
        file_hash = "1" * 64
        envelope_id = create_envelope(
            db_connection,
            file_name="prices_link.xlsx",
            file_hash=file_hash
        )
        effective_date = date(2025, 1, 20)

        try:
            # Act
            price_list_id = create_price_list_entry(
                db_connection,
                envelope_id=envelope_id,
                effective_date=effective_date,
                file_path="/inbox/prices.xlsx",
                discount_percent=10.0
            )

            # Assert
            assert price_list_id is not None
            # psycopg2 возвращает UUID как строку
            assert isinstance(price_list_id, (UUID,
                                              str)), "price_list_id должен быть UUID или строка"

            # Проверить что это валидный UUID
            try:
                UUID(str(price_list_id))
            except ValueError:
                pytest.fail(
                    f"price_list_id не является валидным UUID: {price_list_id}")

            # Проверить связь в БД
            cursor = db_connection.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                           SELECT envelope_id, effective_date, discount_percent
                           FROM price_list
                           WHERE price_list_id = %s
                           """, (price_list_id,))
            record = cursor.fetchone()
            cursor.close()

            assert record is not None
            assert record['envelope_id'] == envelope_id
            assert record['effective_date'] == effective_date
            assert float(record['discount_percent']) == 10.0

        finally:
            cursor = db_connection.cursor()
            cursor.execute("DELETE FROM price_list WHERE price_list_id = %s",
                           (price_list_id,))
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,))
            db_connection.commit()
            cursor.close()

    def test_create_price_list_entry_without_optional_fields(self,
                                                             db_connection):
        """
        Test: Создание price_list с минимальными данными (без optional полей).

        Arrange: Создать envelope
        Act: Создать price_list только с обязательными полями
        Assert: Запись создана, optional поля = NULL
        """
        # Arrange
        file_hash = "2" * 64
        envelope_id = create_envelope(
            db_connection,
            file_name="minimal_price.xlsx",
            file_hash=file_hash
        )
        effective_date = date(2025, 2, 1)

        try:
            # Act
            price_list_id = create_price_list_entry(
                db_connection,
                envelope_id=envelope_id,
                effective_date=effective_date
            )

            # Assert
            cursor = db_connection.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                           SELECT file_path, discount_percent
                           FROM price_list
                           WHERE price_list_id = %s
                           """, (price_list_id,))
            record = cursor.fetchone()
            cursor.close()

            assert record['file_path'] is None
            assert record['discount_percent'] is None

        finally:
            cursor = db_connection.cursor()
            cursor.execute("DELETE FROM price_list WHERE price_list_id = %s",
                           (price_list_id,))
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,))
            db_connection.commit()
            cursor.close()


# =============================================================================
# Integration Tests (End-to-End workflow)
# =============================================================================

@pytest.mark.unit
class TestIdempotencyWorkflow:
    """
    Интеграционные тесты полного workflow идемпотентности.
    """

    def test_full_idempotency_workflow(self, db_connection, tmp_path):
        """
        Test: Полный workflow - создание файла, проверка, envelope, price_list.

        Arrange: Создать тестовый файл
        Act: Выполнить полный цикл идемпотентности
        Assert: Все шаги выполнены корректно
        """
        # Arrange
        test_file = tmp_path / "workflow_test.xlsx"
        test_file.write_text("Test price data", encoding='utf-8')

        # Act & Assert

        # Шаг 1: Вычислить хеш
        file_hash = compute_file_sha256(str(test_file))
        assert len(file_hash) == 64

        # Шаг 2: Проверить что файл новый
        existing = check_file_exists(db_connection, file_hash)
        assert existing is None, "Файл должен быть новым"

        # Шаг 3: Создать envelope
        envelope_id = create_envelope(
            db_connection,
            file_name="workflow_test.xlsx",
            file_hash=file_hash
        )
        assert envelope_id is not None

        # Шаг 4: Обновить статус на success
        update_envelope_status(
            db_connection,
            envelope_id=envelope_id,
            status='success',
            rows_inserted=50
        )

        # Шаг 5: Создать price_list entry
        price_list_id = create_price_list_entry(
            db_connection,
            envelope_id=envelope_id,
            effective_date=date(2025, 1, 15)
        )
        assert price_list_id is not None

        # Шаг 6: Проверить что теперь файл существует
        existing = check_file_exists(db_connection, file_hash)
        assert existing is not None
        assert existing['status'] == 'success'
        assert existing['rows_inserted'] == 50

        # Cleanup
        cursor = db_connection.cursor()
        try:
            cursor.execute("DELETE FROM price_list WHERE price_list_id = %s",
                           (price_list_id,))
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,))
            db_connection.commit()
        finally:
            cursor.close()

    def test_duplicate_file_detection(self, db_connection, tmp_path):
        """
        Test: Обнаружение дубликата файла по SHA256.

        Arrange: Создать файл и импортировать его
        Act: Попытаться импортировать тот же файл повторно
        Assert: Обнаружен дубликат
        """
        # Arrange
        test_file = tmp_path / "duplicate_test.xlsx"
        test_file.write_text("Same content", encoding='utf-8')
        file_hash = compute_file_sha256(str(test_file))

        # Первый импорт
        envelope_id = create_envelope(
            db_connection,
            file_name="duplicate_test.xlsx",
            file_hash=file_hash
        )

        try:
            # Act - попытка повторного импорта
            existing = check_file_exists(db_connection, file_hash)

            # Assert
            assert existing is not None, "Дубликат должен быть обнаружен"
            assert existing['envelope_id'] == envelope_id
            assert existing['file_sha256'] == file_hash

        finally:
            cursor = db_connection.cursor()
            cursor.execute(
                "DELETE FROM ingest_envelope WHERE envelope_id = %s",
                (envelope_id,))
            db_connection.commit()
            cursor.close()
