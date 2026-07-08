<?php

declare(strict_types=1);



/**

 * İlk kurulum: admin şifresini sorar ve public_html/config.php üretir.

 * Mevcut config varsa mail_mode / mail_to / smtp alanlarını bozmadan günceller.

 * Kullanım: php scripts/create_admin_config.php

 *           ADMIN_PASSWORD ortam degiskeni veya --password= (deger repoda tutulmaz)

 *           SMTP_PASS ortam değişkeni veya --set-smtp-pass (etkileşimli) ile smtp_pass yazılır.

 */



$root = dirname(__DIR__);

$configPath = $root . '/public_html/config.php';



$password = null;

$setSmtpPass = false;

$mailModeOverride = null;



foreach ($argv as $arg) {

    if (str_starts_with($arg, '--password=')) {

        $password = substr($arg, strlen('--password='));

    } elseif ($arg === '--set-smtp-pass') {

        $setSmtpPass = true;

    } elseif (str_starts_with($arg, '--mail-mode=')) {

        $mailModeOverride = substr($arg, strlen('--mail-mode='));

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



$allowedMailModes = ['log', 'mail', 'smtp'];

if ($mailModeOverride !== null && in_array($mailModeOverride, $allowedMailModes, true)) {

    $config['mail_mode'] = $mailModeOverride;

} elseif (!isset($config['mail_mode']) || !in_array((string) $config['mail_mode'], $allowedMailModes, true)) {

    $config['mail_mode'] = 'log';

}



if (!isset($config['mail_to']) || trim((string) $config['mail_to']) === '') {

    $config['mail_to'] = 'info@emirgandanismanlik.com';

} elseif (!filter_var((string) $config['mail_to'], FILTER_VALIDATE_EMAIL)) {

    $config['mail_to'] = 'info@emirgandanismanlik.com';

}



if (!isset($config['smtp_host']) || trim((string) $config['smtp_host']) === '') {

    $config['smtp_host'] = 'mail.kurumsaleposta.com';

}



if (!isset($config['smtp_port']) || (!is_int($config['smtp_port']) && !ctype_digit((string) $config['smtp_port']))) {

    $config['smtp_port'] = 465;

} else {

    $config['smtp_port'] = (int) $config['smtp_port'];

}



if (!isset($config['smtp_secure']) || !in_array((string) $config['smtp_secure'], ['ssl', 'tls', ''], true)) {

    $config['smtp_secure'] = 'ssl';

}



if (!isset($config['smtp_user']) || trim((string) $config['smtp_user']) === '') {

    $config['smtp_user'] = 'info@emirgandanismanlik.com';

} elseif (!filter_var((string) $config['smtp_user'], FILTER_VALIDATE_EMAIL)) {

    $config['smtp_user'] = 'info@emirgandanismanlik.com';

}



$smtpPassEnv = getenv('SMTP_PASS');

if ($smtpPassEnv !== false && $smtpPassEnv !== '') {

    $config['smtp_pass'] = $smtpPassEnv;

} elseif ($setSmtpPass) {

    if (PHP_SAPI !== 'cli') {

        fwrite(STDERR, "Bu betik yalnızca CLI'dan çalıştırılabilir.\n");

        exit(1);

    }

    if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {

        fwrite(STDOUT, "SMTP şifresi: ");

        $smtpPassInput = trim((string) fgets(STDIN));

    } else {

        fwrite(STDOUT, "SMTP şifresi: ");

        system('stty -echo');

        $smtpPassInput = trim((string) fgets(STDIN));

        system('stty echo');

        fwrite(STDOUT, "\n");

    }

    if ($smtpPassInput !== '') {

        $config['smtp_pass'] = $smtpPassInput;

    }

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

