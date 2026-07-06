<?php
declare(strict_types=1);

/**
 * İçerik dosyasını yükler ve JSON olarak döndürür.
 */
function load_content(): array
{
    $path = dirname(__DIR__) . '/content/content.json';

    if (!is_readable($path)) {
        http_response_code(500);
        echo 'İçerik dosyası okunamadı.';
        exit;
    }

    $json = file_get_contents($path);
    $data = json_decode($json, true, 512, JSON_THROW_ON_ERROR);

    if (!is_array($data)) {
        throw new RuntimeException('Geçersiz içerik formatı.');
    }

    return $data;
}

/**
 * HTML çıktısı için güvenli metin.
 */
function e(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
