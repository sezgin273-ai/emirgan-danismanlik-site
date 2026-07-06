<?php
declare(strict_types=1);

const UPLOAD_MAX_BYTES = 5 * 1024 * 1024;
const UPLOAD_ALLOWED_EXT = ['png', 'jpg', 'jpeg', 'webp'];
const UPLOAD_ALLOWED_MIME = [
    'image/png',
    'image/jpeg',
    'image/webp',
];

function uploads_dir(): string
{
    return dirname(__DIR__) . '/assets/img/uploads';
}

function uploads_url_prefix(): string
{
    return '/assets/img/uploads';
}

function ensure_uploads_dir(): bool
{
    $dir = uploads_dir();
    if (is_dir($dir)) {
        return true;
    }

    return mkdir($dir, 0755, true) || is_dir($dir);
}

function detect_image_mime(string $tmp): string
{
    if (class_exists('finfo')) {
        $finfo = new finfo(FILEINFO_MIME_TYPE);
        $mime = $finfo->file($tmp) ?: '';
        if ($mime !== '') {
            return $mime;
        }
    }

    $info = @getimagesize($tmp);
    if (is_array($info) && isset($info['mime'])) {
        return (string) $info['mime'];
    }

    return '';
}


function validate_uploaded_image(array $file): ?string
{
    if (($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
        return 'Dosya yüklenemedi.';
    }

    if (($file['size'] ?? 0) > UPLOAD_MAX_BYTES) {
        return 'Dosya 5 MB sınırını aşıyor.';
    }

    $name = (string) ($file['name'] ?? '');
    $ext = strtolower(pathinfo($name, PATHINFO_EXTENSION));
    if (!in_array($ext, UPLOAD_ALLOWED_EXT, true)) {
        return 'Yalnızca PNG, JPG veya WebP yüklenebilir.';
    }

    $tmp = (string) ($file['tmp_name'] ?? '');
    if ($tmp === '' || !is_uploaded_file($tmp)) {
        return 'Geçersiz yükleme.';
    }

    $mime = detect_image_mime($tmp);
    if (!in_array($mime, UPLOAD_ALLOWED_MIME, true)) {
        return 'Geçersiz dosya türü.';
    }

    return null;
}

function random_upload_basename(string $ext): string
{
    return bin2hex(random_bytes(16)) . '.' . $ext;
}

function save_uploaded_team_photo(array $file): array
{
    $error = validate_uploaded_image($file);
    if ($error !== null) {
        return ['ok' => false, 'error' => $error];
    }

    if (!extension_loaded('gd')) {
        return ['ok' => false, 'error' => 'GD eklentisi gerekli.'];
    }

    if (!ensure_uploads_dir()) {
        return ['ok' => false, 'error' => 'Yükleme klasörü oluşturulamadı.'];
    }

    $name = (string) $file['name'];
    $ext = strtolower(pathinfo($name, PATHINFO_EXTENSION));
    if ($ext === 'jpeg') {
        $ext = 'jpg';
    }

    $tmp = (string) $file['tmp_name'];
    $mime = detect_image_mime($tmp);
    $src = match ($mime) {
        'image/png' => imagecreatefrompng($tmp),
        'image/jpeg' => imagecreatefromjpeg($tmp),
        'image/webp' => imagecreatefromwebp($tmp),
        default => false,
    };

    if ($src === false) {
        return ['ok' => false, 'error' => 'Görsel okunamadı.'];
    }

    $width = imagesx($src);
    $height = imagesy($src);
    $size = min($width, $height);
    $sx = (int) floor(($width - $size) / 2);
    $sy = (int) floor(($height - $size) / 2);

    $cropped = imagecreatetruecolor(480, 480);
    if ($cropped === false) {
        imagedestroy($src);
        return ['ok' => false, 'error' => 'Görsel işlenemedi.'];
    }

    imagecopyresampled($cropped, $src, 0, 0, $sx, $sy, 480, 480, $size, $size);
    imagedestroy($src);

    $basename = random_upload_basename($ext === 'jpg' ? 'jpg' : $ext);
    $dest = uploads_dir() . '/' . $basename;

    $saved = match ($ext) {
        'png' => imagepng($cropped, $dest, 6),
        'webp' => imagewebp($cropped, $dest, 82),
        default => imagejpeg($cropped, $dest, 85),
    };
    imagedestroy($cropped);

    if (!$saved) {
        return ['ok' => false, 'error' => 'Dosya kaydedilemedi.'];
    }

    return [
        'ok' => true,
        'path' => uploads_url_prefix() . '/' . $basename,
    ];
}

function save_uploaded_brand_image(array $file, string $prefix): array
{
    $error = validate_uploaded_image($file);
    if ($error !== null) {
        return ['ok' => false, 'error' => $error];
    }

    if (!ensure_uploads_dir()) {
        return ['ok' => false, 'error' => 'Yükleme klasörü oluşturulamadı.'];
    }

    $name = (string) $file['name'];
    $ext = strtolower(pathinfo($name, PATHINFO_EXTENSION));
    if ($ext === 'jpeg') {
        $ext = 'jpg';
    }

    $basename = $prefix . '-' . random_upload_basename($ext);
    $dest = uploads_dir() . '/' . $basename;

    if (!move_uploaded_file((string) $file['tmp_name'], $dest)) {
        return ['ok' => false, 'error' => 'Dosya kaydedilemedi.'];
    }

    return [
        'ok' => true,
        'path' => uploads_url_prefix() . '/' . $basename,
    ];
}

function delete_uploaded_file(?string $publicPath): void
{
    if ($publicPath === null || $publicPath === '') {
        return;
    }

    $prefix = uploads_url_prefix() . '/';
    if (!str_starts_with($publicPath, $prefix)) {
        return;
    }

    $basename = basename($publicPath);
    $full = uploads_dir() . '/' . $basename;
    if (is_file($full)) {
        @unlink($full);
    }
}
