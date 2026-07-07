<?php
declare(strict_types=1);

/**
 * İlk kurulum: admin şifresini sorar ve public_html/config.php üretir.
 * Mevcut config varsa mail_mode / mail_to alanlarını bozmadan günceller.
 * Kullanım: php scripts/create_admin_config.php
 *           php scripts/create_admin_config.php --password="***REMOVED***"
 */

$root = dirname(__DIR__);
$configPath = $root . '/public_html/config.php';

$password = null;
foreach ($argv as $arg) {
    if (str_starts_with($arg, '--password=')) {
        $password = substr($arg, strlen('--password='));
    }
}

$existing = [];
if (is_readable($configPath)) {
    $loaded = require $configPath;
    if (is_array($loaded)) {
        $existing = $loaded;
    }
}

if ($password === null || $password === '') {
    if (!empty($existing['admin_password_hash'])) {
        $password = null;
    } else {
        if (PHP_SAPI !== 'cli') {
            fwrite(STDERR, "Bu betik yalnızca CLI'dan çalıştırılabilir.\n");
            exit(1);
        }

        fwrite(STDOUT, "Admin şifresi: ");
        $password = trim((string) fgets(STDIN));
        fwrite(STDOUT, "Şifre tekrar: ");
        $confirm = trim((string) fgets(STDIN));

        if ($password === '' || $password !== $confirm) {
            fwrite(STDERR, "Şifreler eşleşmiyor veya boş.\n");
            exit(1);
        }
    }
}

if ($password !== null && strlen($password) < 8) {
    fwrite(STDERR, "Şifre en az 8 karakter olmalı.\n");
    exit(1);
}

$config = $existing;
if ($password !== null && $password !== '') {
    $config['admin_password_hash'] = password_hash($password, PASSWORD_DEFAULT);
}

if (!isset($config['mail_mode']) || !in_array((string) $config['mail_mode'], ['log', 'mail'], true)) {
    $config['mail_mode'] = 'log';
}

if (!isset($config['mail_to']) || trim((string) $config['mail_to']) === '') {
    $config['mail_to'] = 'info@emirgandanismanlik.com';
}

if (empty($config['admin_password_hash'])) {
    fwrite(STDERR, "admin_password_hash eksik. --password ile çalıştırın.\n");
    exit(1);
}

$lines = ["<?php", "declare(strict_types=1);", "", "/**", " * Admin panel yapılandırması — bu dosya .gitignore ile hariç tutulur.", " * Oluşturma: php scripts/create_admin_config.php", " */", "return ["];
foreach ($config as $key => $value) {
    $lines[] = '    ' . var_export((string) $key, true) . ' => ' . var_export($value, true) . ',';
}
$lines[] = '];';
$lines[] = '';
$content = implode("\n", $lines);

if (file_put_contents($configPath, $content, LOCK_EX) === false) {
    fwrite(STDERR, "config.php yazılamadı: {$configPath}\n");
    exit(1);
}

fwrite(STDOUT, "config.php oluşturuldu: {$configPath}\n");
fwrite(STDOUT, "Şifre depoya kaydedilmedi.\n");
