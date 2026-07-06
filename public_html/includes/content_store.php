<?php
declare(strict_types=1);

const CONTENT_BACKUP_MAX = 20;

function content_file_path(): string
{
    return dirname(__DIR__, 2) . '/content/content.json';
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

function create_content_backup(): ?string
{
    $source = content_file_path();
    if (!is_readable($source)) {
        return null;
    }

    $dir = content_backup_dir();
    if (!is_dir($dir) && !mkdir($dir, 0755, true) && !is_dir($dir)) {
        return null;
    }

    $name = 'content-' . date('Y-m-d_His') . '.json';
    $dest = $dir . '/' . $name;
    if (!copy($source, $dest)) {
        return null;
    }

    $files = glob($dir . '/content-*.json') ?: [];
    usort($files, static fn(string $a, string $b): int => filemtime($b) <=> filemtime($a));
    foreach (array_slice($files, CONTENT_BACKUP_MAX) as $old) {
        @unlink($old);
    }

    return $name;
}

function list_content_backups(): array
{
    $dir = content_backup_dir();
    if (!is_dir($dir)) {
        return [];
    }

    $files = glob($dir . '/content-*.json') ?: [];
    usort($files, static fn(string $a, string $b): int => filemtime($b) <=> filemtime($a));

    return array_map(static fn(string $path): array => [
        'name' => basename($path),
        'mtime' => filemtime($path) ?: 0,
        'size' => filesize($path) ?: 0,
    ], $files);
}

function restore_content_backup(string $name): bool
{
    if (!preg_match('/^content-[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}\.json$/', $name)) {
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

    return save_content($data, true);
}

function save_content(array $data, bool $backup = true): bool
{
    try {
        $json = encode_content($data);
    } catch (JsonException) {
        return false;
    }

    if ($backup) {
        create_content_backup();
    }

    $path = content_file_path();
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

function section_visible(array $content, string $sectionId): bool
{
    return ($content['site']['sections'][$sectionId]['visible'] ?? true) === true;
}
