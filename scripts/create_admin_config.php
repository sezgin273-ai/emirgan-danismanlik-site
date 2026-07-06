<?php
declare(strict_types=1);

/**
 * İlk kurulum: admin şifresini sorar ve public_html/config.php üretir.
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

if ($password === null || $password === '') {
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

if (strlen($password) < 8) {
    fwrite(STDERR, "Şifre en az 8 karakter olmalı.\n");
    exit(1);
}

$hash = password_hash($password, PASSWORD_DEFAULT);
$content = "<?php\n"
    . "declare(strict_types=1);\n\n"
    . "/**\n"
    . " * Admin panel yapılandırması — bu dosya .gitignore ile hariç tutulur.\n"
    . " * Oluşturma: php scripts/create_admin_config.php\n"
    . " */\n"
    . "return [\n"
    . "    'admin_password_hash' => " . var_export($hash, true) . ",\n"
    . "];\n";

if (file_put_contents($configPath, $content, LOCK_EX) === false) {
    fwrite(STDERR, "config.php yazılamadı: {$configPath}\n");
    exit(1);
}

fwrite(STDOUT, "config.php oluşturuldu: {$configPath}\n");
fwrite(STDOUT, "Şifre depoya kaydedilmedi.\n");
