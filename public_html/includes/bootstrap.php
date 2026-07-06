<?php
declare(strict_types=1);

/**
 * İçerik dosyasını yükler ve JSON olarak döndürür.
 */
function load_content(): array
{
    $path = dirname(__DIR__, 2) . '/content/content.json';

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

/**
 * UTF-8 güvenli tek karakter (mbstring yoksa preg fallback).
 */
function utf8_char_at(string $value, int $index): string
{
    if (function_exists('mb_substr')) {
        return mb_substr($value, $index, 1, 'UTF-8');
    }

    preg_match_all('/./us', $value, $matches);
    $chars = $matches[0] ?? [];

    return $chars[$index] ?? '';
}

/**
 * UTF-8 güvenli büyük harf.
 */
function utf8_strtoupper(string $value): string
{
    if (function_exists('mb_strtoupper')) {
        return mb_strtoupper($value, 'UTF-8');
    }

    return strtoupper($value);
}

/**
 * İsimden monogram baş harfleri üretir.
 */
function initials(string $name): string
{
    $parts = preg_split('/\s+/u', trim($name)) ?: [];
    if ($parts === []) {
        return '';
    }

    $first = utf8_char_at($parts[0], 0);
    $last = utf8_char_at($parts[count($parts) - 1], 0);

    return utf8_strtoupper($first . $last);
}

/**
 * Hizmet ikonu SVG döndürür.
 */
function service_icon(string $icon): string
{
    $icons = [
        'strategy' => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 17l6-6 4 4 7-7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M14 8h7v7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        'legal' => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v3M8 6h8M6 9h12v10H6zM9 13h6M9 16h4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        'finance' => '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="18" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M7 10h2M15 14h2M12 10v4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        'feasibility' => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 18V6M4 18h16M8 14v-3M12 16V9M16 12V7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        'realestate' => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10l8-6 8 6v9H4z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M10 19v-5h4v5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>',
        'trade' => '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M3 12h18M12 4c2 2.5 2 11.5 0 16M12 4c-2 2.5-2 11.5 0 16" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>',
        'governance' => '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="16" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M4 19c0-2.5 2-4 4-4s4 1.5 4 4M12 19c0-2.5 2-4 4-4s4 1.5 4 4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    ];

    return $icons[$icon] ?? $icons['strategy'];
}

/**
 * Faaliyet rozeti ikonu SVG döndürür.
 */
function badge_icon(string $icon): string
{
    $icons = [
        'energy' => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2L5 14h6l-1 8 8-12h-6l1-8z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>',
        'realestate' => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10l8-6 8 6v9H4z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>',
        'trade' => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7h10v10H7zM4 4h4M16 4h4M4 16h4M16 16h4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        'construction' => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 20h18M6 20V9l6-4 6 4v11M10 20v-5h4v5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>',
        'investment' => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 18V6M4 18h16M8 14v-3M12 16V9M16 12V7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    ];

    return $icons[$icon] ?? $icons['energy'];
}
