<?php
declare(strict_types=1);

require_once __DIR__ . '/content_store.php';

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
 * Geçerli hizmet ikon adlarını döndürür.
 *
 * @return list<string>
 */
function service_icon_names(): array
{
    return ['strategy', 'legal', 'finance', 'feasibility', 'realestate', 'trade', 'governance'];
}

/**
 * Hizmet ikonu whitelist doğrulaması.
 */
function is_valid_service_icon(string $icon): bool
{
    return in_array($icon, service_icon_names(), true);
}

/**
 * Süreç bölümü ön yüzde render edilebilir mi?
 */
function process_section_renderable(array $content): bool
{
    if (!section_visible($content, 'process')) {
        return false;
    }

    $steps = $content['process']['steps'] ?? null;

    return is_array($steps) && $steps !== [];
}

/**
 * Hero watermark etkin mi? (varsayılan: açık)
 */
function hero_watermark_enabled(array $content): bool
{
    return ($content['hero']['watermark_enabled'] ?? true) !== false;
}

/**
 * İletişim bilgi öğeleri (info_items).
 *
 * @return list<array{type:string,title:string,value:string}>
 */
function contact_info_items(array $content): array
{
    $items = $content['contact']['info_items'] ?? [];
    if (!is_array($items)) {
        return [];
    }

    return array_values(array_filter($items, static fn($item) => is_array($item)));
}

/**
 * İletişim — ilk address tipli öğenin değeri (harita için).
 */
function contact_first_address_text(array $content): string
{
    foreach (contact_info_items($content) as $item) {
        if (($item['type'] ?? '') === 'address') {
            $value = trim((string) ($item['value'] ?? ''));
            if ($value !== '') {
                return $value;
            }
        }
    }

    return '';
}

/**
 * Google Haritalar embed URL (API anahtarsız; info_items ilk address kaydından).
 */
function contact_turkey_map_embed_url(array $content): string
{
    $text = contact_first_address_text($content);
    if ($text === '') {
        return '';
    }

    return 'https://www.google.com/maps?q=' . rawurlencode($text) . '&output=embed';
}

/** @return list<string> */
function display_size_options(): array
{
    return ['small', 'medium', 'large'];
}

function is_valid_display_size(string $size): bool
{
    return in_array($size, display_size_options(), true);
}

/** @return list<string> */
function display_size_groups(): array
{
    return ['header_logo', 'footer_logo', 'team_avatar', 'service_icon', 'hero_emblem'];
}

function is_valid_display_group(string $group): bool
{
    return in_array($group, display_size_groups(), true);
}

function display_size_value(array $content, string $group): string
{
    $size = (string) ($content['display'][$group] ?? 'medium');

    return is_valid_display_size($size) ? $size : 'medium';
}

function display_size_class(array $content, string $group): string
{
    $size = display_size_value($content, $group);

    return 'display-' . str_replace('_', '-', $group) . '-' . $size;
}

function display_body_classes(array $content): string
{
    $classes = [];
    foreach (display_size_groups() as $group) {
        $classes[] = display_size_class($content, $group);
    }

    return implode(' ', $classes);
}

function is_valid_contact_info_type(string $type): bool
{
    return in_array($type, ['address', 'phone', 'fax', 'email', 'other'], true);
}

/**
 * Hizmet ikonu SVG döndürür.
 */
function service_icon(string $icon): string
{
    if ($icon === '' || !is_valid_service_icon($icon)) {
        $icon = 'strategy';
    }

    $attrs = 'viewBox="0 0 24 24" aria-hidden="true" focusable="false"';
    $icons = [
        'strategy' => '<svg ' . $attrs . '><path d="M3 17l6-6 4 4 7-7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M14 8h7v7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        'legal' => '<svg ' . $attrs . '><path d="M12 2v4M8 6h8M5 9h14v12H5zM9 13h6M9 17h4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        'finance' => '<svg ' . $attrs . '><rect x="3" y="5" width="18" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M7 10h2M15 14h2M12 9v6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        'feasibility' => '<svg ' . $attrs . '><path d="M4 19V5M4 19h16M8 15v-4M12 17V9M16 13V7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        'realestate' => '<svg ' . $attrs . '><path d="M3 11l9-7 9 7v10H3z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M9 21v-6h6v6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        'trade' => '<svg ' . $attrs . '><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M2 12h20M12 3c2.2 2.8 2.2 13.2 0 18M12 3c-2.2 2.8-2.2 13.2 0 18" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>',
        'governance' => '<svg ' . $attrs . '><circle cx="7" cy="7" r="3.5" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="17" cy="7" r="3.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M3 20c0-2.8 2.2-5 4.5-5s4.5 2.2 4.5 5M13 20c0-2.8 2.2-5 4.5-5s4.5 2.2 4.5 5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
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
