<?php
declare(strict_types=1);

const CONTENT_BACKUP_MAX = 20;

function content_file_path(): string
{
    return content_file_path_for_lang(SITE_LANG_DEFAULT);
}

function content_file_path_for_lang(string $lang): string
{
    $lang = strtolower(trim($lang));
    if ($lang === SITE_LANG_DEFAULT) {
        return dirname(__DIR__, 2) . '/content/content.json';
    }
    if (!in_array($lang, SITE_LANGS, true)) {
        throw new InvalidArgumentException('Geçersiz dil kodu.');
    }

    return dirname(__DIR__, 2) . '/content/content.' . $lang . '.json';
}

function content_backup_prefix_for_lang(string $lang): string
{
    return $lang === SITE_LANG_DEFAULT ? 'content' : 'content-' . $lang;
}

function content_backup_dir(): string
{
    return dirname(__DIR__, 2) . '/content/backups';
}

function encode_content(array $data): string
{
    $json = json_encode(
        $data,
        JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR
    );
    json_decode($json, true, 512, JSON_THROW_ON_ERROR);

    return $json . "\n";
}

function create_content_backup(?string $lang = null): ?string
{
    $lang = $lang ?? SITE_LANG_DEFAULT;
    $source = content_file_path_for_lang($lang);
    if (!is_readable($source)) {
        return null;
    }

    $dir = content_backup_dir();
    if (!is_dir($dir) && !mkdir($dir, 0755, true) && !is_dir($dir)) {
        return null;
    }

    $prefix = content_backup_prefix_for_lang($lang);
    $name = $prefix . '-' . date('Y-m-d_His') . '.json';
    $dest = $dir . '/' . $name;
    if (!copy($source, $dest)) {
        return null;
    }

    $pattern = $dir . '/' . $prefix . '-*.json';
    $files = glob($pattern) ?: [];
    usort($files, static fn(string $a, string $b): int => filemtime($b) <=> filemtime($a));
    foreach (array_slice($files, CONTENT_BACKUP_MAX) as $old) {
        @unlink($old);
    }

    return $name;
}

function list_content_backups(?string $lang = null): array
{
    $lang = $lang ?? SITE_LANG_DEFAULT;
    $prefix = content_backup_prefix_for_lang($lang);
    $dir = content_backup_dir();
    if (!is_dir($dir)) {
        return [];
    }

    $files = glob($dir . '/' . $prefix . '-*.json') ?: [];
    usort($files, static fn(string $a, string $b): int => filemtime($b) <=> filemtime($a));

    return array_map(static fn(string $path): array => [
        'name' => basename($path),
        'mtime' => filemtime($path) ?: 0,
        'size' => filesize($path) ?: 0,
    ], $files);
}

function restore_content_backup(string $name, ?string $lang = null): bool
{
    $lang = $lang ?? SITE_LANG_DEFAULT;
    if (!is_valid_backup_name($name, $lang)) {
        return false;
    }

    $path = content_backup_dir() . '/' . $name;
    if (!is_readable($path)) {
        return false;
    }

    $json = file_get_contents($path);
    if ($json === false) {
        return false;
    }

    $data = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
    if (!is_array($data)) {
        return false;
    }

    return save_content_for_lang($lang, $data, true);
}

function save_content_for_lang(string $lang, array $data, bool $backup = true): bool
{
    try {
        $json = encode_content($data);
    } catch (JsonException) {
        return false;
    }

    if ($backup) {
        create_content_backup($lang);
    }

    $path = content_file_path_for_lang($lang);
    $tmp = $path . '.tmp.' . getmypid() . '.' . bin2hex(random_bytes(4));
    $fp = fopen($tmp, 'c+b');
    if ($fp === false) {
        return false;
    }

    try {
        if (!flock($fp, LOCK_EX)) {
            return false;
        }
        ftruncate($fp, 0);
        if (fwrite($fp, $json) === false) {
            return false;
        }
        fflush($fp);
        flock($fp, LOCK_UN);
    } finally {
        fclose($fp);
    }

    if (!rename($tmp, $path)) {
        @unlink($tmp);
        return false;
    }

    return true;
}

function save_content(array $data, bool $backup = true): bool
{
    return save_content_for_lang(SITE_LANG_DEFAULT, $data, $backup);
}

function section_visible(array $content, string $sectionId): bool
{
    return ($content['site']['sections'][$sectionId]['visible'] ?? true) === true;
}

function is_valid_backup_name(string $name, ?string $lang = null): bool
{
    if (str_contains($name, '..') || str_contains($name, '/') || str_contains($name, '\\')) {
        return false;
    }

    $lang = $lang ?? SITE_LANG_DEFAULT;
    $prefix = content_backup_prefix_for_lang($lang);

    return (bool) preg_match('/^' . preg_quote($prefix, '/') . '-[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}\.json$/', $name);
}

function backup_labels_path(): string
{
    return content_backup_dir() . '/.labels.json';
}

function load_backup_labels(): array
{
    $path = backup_labels_path();
    if (!is_readable($path)) {
        return [];
    }
    $data = json_decode((string) file_get_contents($path), true);

    return is_array($data) ? $data : [];
}

function save_backup_labels(array $labels): bool
{
    $dir = content_backup_dir();
    if (!is_dir($dir) && !mkdir($dir, 0755, true) && !is_dir($dir)) {
        return false;
    }
    $json = json_encode($labels, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);

    return file_put_contents(backup_labels_path(), $json . "\n", LOCK_EX) !== false;
}

function sanitize_backup_label(string $label): ?string
{
    $label = str_replace(["\r", "\n", "\0"], '', trim($label));
    $len = function_exists('mb_strlen') ? mb_strlen($label, 'UTF-8') : strlen($label);
    if ($label === '' || $len > 50) {
        return null;
    }
    if (!preg_match('/^[\p{L}\p{N}\s\-_]+$/u', $label)) {
        return null;
    }

    return $label;
}

function delete_content_backup(string $name, ?string $lang = null): bool
{
    $lang = $lang ?? SITE_LANG_DEFAULT;
    if (!is_valid_backup_name($name, $lang)) {
        return false;
    }
    $path = content_backup_dir() . '/' . $name;
    if (!is_file($path)) {
        return false;
    }
    if (!unlink($path)) {
        return false;
    }
    $labels = load_backup_labels();
    if (isset($labels[$name])) {
        unset($labels[$name]);
        save_backup_labels($labels);
    }

    return true;
}

function set_backup_label(string $name, string $label, ?string $lang = null): bool
{
    $lang = $lang ?? SITE_LANG_DEFAULT;
    if (!is_valid_backup_name($name, $lang)) {
        return false;
    }
    $path = content_backup_dir() . '/' . $name;
    if (!is_file($path)) {
        return false;
    }
    $clean = sanitize_backup_label($label);
    if ($clean === null) {
        return false;
    }
    $labels = load_backup_labels();
    $labels[$name] = $clean;

    return save_backup_labels($labels);
}

function list_content_backups_with_labels(?string $lang = null): array
{
    $backups = list_content_backups($lang);
    $labels = load_backup_labels();
    foreach ($backups as $i => $backup) {
        $backups[$i]['label'] = $labels[$backup['name']] ?? '';
        $backups[$i]['is_latest'] = $i === 0;
    }

    return $backups;
}
