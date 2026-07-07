<?php
declare(strict_types=1);

require_once __DIR__ . '/../includes/bootstrap.php';
require_once __DIR__ . '/../includes/admin_auth.php';
require_once __DIR__ . '/../includes/image_upload.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo 'Method Not Allowed';
    exit;
}

if (!admin_verify_csrf($_POST['csrf_token'] ?? null)) {
    admin_csrf_fail();
}

admin_require_login();

$action = (string) ($_POST['action'] ?? '');
$redirect = '/admin/dashboard.php';
$flash = 'ok';

function admin_redirect(string $url, string $flash, string $message = ''): never
{
    admin_start_session();
    $_SESSION['admin_flash'] = ['type' => $flash, 'message' => $message];
    header('Location: ' . $url, true, 302);
    exit;
}

function admin_abort_with_status(int $statusCode, string $message): never
{
    http_response_code($statusCode);
    header('Content-Type: text/plain; charset=UTF-8');
    echo $message;
    exit;
}

function admin_normalize_content(array $posted, array $current): array
{
    $content = $current;

    if (isset($posted['site']) && is_array($posted['site'])) {
        $content['site']['title'] = trim((string) ($posted['site']['title'] ?? $content['site']['title']));
        $content['site']['lang'] = trim((string) ($posted['site']['lang'] ?? $content['site']['lang']));
        if (isset($posted['site']['meta']) && is_array($posted['site']['meta'])) {
            foreach (['description', 'og_title', 'og_description'] as $key) {
                $content['site']['meta'][$key] = trim((string) ($posted['site']['meta'][$key] ?? $content['site']['meta'][$key] ?? ''));
            }
        }
        if (isset($posted['site']['sections']) && is_array($posted['site']['sections'])) {
            foreach ($content['site']['sections'] as $sid => $section) {
                if (array_key_exists($sid, $posted['site']['sections'])) {
                    $content['site']['sections'][$sid]['visible'] = !empty(
                        $posted['site']['sections'][$sid]['visible']
                    );
                }
            }
        }
    }

    foreach (['hero', 'vision', 'mission', 'footer'] as $key) {
        if (!isset($posted[$key]) || !is_array($posted[$key])) {
            continue;
        }
        foreach ($posted[$key] as $field => $value) {
            if (is_string($value)) {
                $content[$key][$field] = trim($value);
            }
        }
    }

    if (isset($posted['hero']) && is_array($posted['hero'])) {
        $content['hero']['watermark_enabled'] = !empty($posted['hero']['watermark_enabled']);
    }

    if (isset($posted['intro']) && is_array($posted['intro'])) {
        $content['intro']['title'] = trim((string) ($posted['intro']['title'] ?? $content['intro']['title']));
        $content['intro']['text'] = trim((string) ($posted['intro']['text'] ?? $content['intro']['text']));
        if (isset($posted['intro']['badges']) && is_array($posted['intro']['badges'])) {
            $badges = [];
            foreach ($posted['intro']['badges'] as $badge) {
                if (!is_array($badge)) {
                    continue;
                }
                $label = trim((string) ($badge['label'] ?? ''));
                if ($label === '') {
                    continue;
                }
                $badges[] = [
                    'icon' => trim((string) ($badge['icon'] ?? 'energy')),
                    'label' => $label,
                ];
            }
            $content['intro']['badges'] = $badges;
        }
    }

    if (isset($posted['about']) && is_array($posted['about'])) {
        $content['about']['title'] = trim((string) ($posted['about']['title'] ?? $content['about']['title']));
        $content['about']['heading'] = trim((string) ($posted['about']['heading'] ?? $content['about']['heading']));
        if (isset($posted['about']['paragraphs']) && is_array($posted['about']['paragraphs'])) {
            $content['about']['paragraphs'] = array_values(array_filter(
                array_map(static fn($p) => trim((string) $p), $posted['about']['paragraphs']),
                static fn(string $p) => $p !== ''
            ));
        }
    }

    if (isset($posted['services']) && is_array($posted['services'])) {
        $content['services']['title'] = trim((string) ($posted['services']['title'] ?? $content['services']['title']));
        if (isset($posted['services']['items']) && is_array($posted['services']['items'])) {
            $items = [];
            foreach ($posted['services']['items'] as $item) {
                if (!is_array($item)) {
                    continue;
                }
                $title = trim((string) ($item['title'] ?? ''));
                if ($title === '') {
                    continue;
                }
                $icon = trim((string) ($item['icon'] ?? ''));
                if ($icon === '') {
                    $icon = 'strategy';
                }
                if (!is_valid_service_icon($icon)) {
                    admin_abort_with_status(422, 'Geçersiz hizmet ikonu.');
                }
                $items[] = [
                    'title' => $title,
                    'description' => trim((string) ($item['description'] ?? '')),
                    'icon' => $icon,
                ];
            }
            $content['services']['items'] = $items;
        }
    }

    if (isset($posted['process']) && is_array($posted['process'])) {
        if (!isset($content['process']) || !is_array($content['process'])) {
            $content['process'] = ['title' => '', 'steps' => []];
        }
        $content['process']['title'] = trim((string) ($posted['process']['title'] ?? $content['process']['title'] ?? ''));
        if (isset($posted['process']['steps']) && is_array($posted['process']['steps'])) {
            $steps = [];
            foreach ($posted['process']['steps'] as $step) {
                if (!is_array($step)) {
                    continue;
                }
                $title = trim((string) ($step['title'] ?? ''));
                if ($title === '') {
                    continue;
                }
                $steps[] = [
                    'title' => $title,
                    'description' => trim((string) ($step['description'] ?? '')),
                ];
            }
            $content['process']['steps'] = $steps;
        }
    }

    if (isset($posted['team']) && is_array($posted['team'])) {
        $content['team']['title'] = trim((string) ($posted['team']['title'] ?? $content['team']['title']));
        $content['team']['intro'] = trim((string) ($posted['team']['intro'] ?? $content['team']['intro']));
        if (isset($posted['team']['members']) && is_array($posted['team']['members'])) {
            $members = [];
            foreach ($posted['team']['members'] as $idx => $member) {
                if (!is_array($member)) {
                    continue;
                }
                $name = trim((string) ($member['name'] ?? ''));
                if ($name === '') {
                    continue;
                }
                $photo = trim((string) ($member['photo'] ?? ''));
                $members[] = [
                    'name' => $name,
                    'title' => trim((string) ($member['title'] ?? '')),
                    'description' => trim((string) ($member['description'] ?? '')),
                    'photo' => $photo,
                ];
            }
            $content['team']['members'] = $members;
        }
    }

    if (isset($posted['contact']) && is_array($posted['contact'])) {
        $content['contact']['title'] = trim((string) ($posted['contact']['title'] ?? $content['contact']['title']));
        $content['contact']['heading'] = trim((string) ($posted['contact']['heading'] ?? $content['contact']['heading']));
        $content['contact']['email'] = trim((string) ($posted['contact']['email'] ?? $content['contact']['email']));
        if (isset($posted['contact']['addresses']) && is_array($posted['contact']['addresses'])) {
            $addresses = [];
            foreach ($posted['contact']['addresses'] as $addr) {
                if (!is_array($addr)) {
                    continue;
                }
                $label = trim((string) ($addr['label'] ?? ''));
                if ($label === '') {
                    continue;
                }
                $addresses[] = [
                    'label' => $label,
                    'text' => trim((string) ($addr['text'] ?? '')),
                ];
            }
            $content['contact']['addresses'] = $addresses;
        }
        if (isset($posted['contact']['form']) && is_array($posted['contact']['form'])) {
            foreach ($posted['contact']['form'] as $field => $value) {
                if ($field === 'submit' || $field === 'success' || $field === 'error') {
                    $content['contact']['form'][$field] = trim((string) $value);
                } elseif (is_array($value)) {
                    $content['contact']['form'][$field] = [
                        'label' => trim((string) ($value['label'] ?? '')),
                        'placeholder' => trim((string) ($value['placeholder'] ?? '')),
                    ];
                }
            }
        }
    }

    if (isset($posted['navigation']) && is_array($posted['navigation'])) {
        if (isset($posted['navigation']['items']) && is_array($posted['navigation']['items'])) {
            foreach ($posted['navigation']['items'] as $idx => $item) {
                if (!is_array($item)) {
                    continue;
                }
                if (isset($content['navigation']['items'][$idx])) {
                    $content['navigation']['items'][$idx]['label'] = trim((string) ($item['label'] ?? $content['navigation']['items'][$idx]['label']));
                }
            }
        }
        if (isset($posted['navigation']['cta']) && is_array($posted['navigation']['cta'])) {
            $content['navigation']['cta']['label'] = trim((string) ($posted['navigation']['cta']['label'] ?? $content['navigation']['cta']['label']));
        }
    }

    if (isset($posted['ui']) && is_array($posted['ui'])) {
        foreach ($posted['ui'] as $key => $value) {
            if (is_string($value)) {
                $content['ui'][$key] = trim($value);
            }
        }
    }

    if (isset($posted['kvkk']) && is_array($posted['kvkk'])) {
        $content['kvkk']['title'] = trim((string) ($posted['kvkk']['title'] ?? $content['kvkk']['title']));
        $content['kvkk']['intro'] = trim((string) ($posted['kvkk']['intro'] ?? $content['kvkk']['intro']));
        $content['kvkk']['note'] = trim((string) ($posted['kvkk']['note'] ?? $content['kvkk']['note'] ?? ''));
        if (isset($posted['kvkk']['sections']) && is_array($posted['kvkk']['sections'])) {
            $sections = [];
            foreach ($posted['kvkk']['sections'] as $section) {
                if (!is_array($section)) {
                    continue;
                }
                $heading = trim((string) ($section['heading'] ?? ''));
                if ($heading === '') {
                    continue;
                }
                $paragraphs = [];
                if (isset($section['paragraphs']) && is_array($section['paragraphs'])) {
                    $paragraphs = array_values(array_filter(
                        array_map(static fn($p) => trim((string) $p), $section['paragraphs']),
                        static fn(string $p) => $p !== ''
                    ));
                }
                $sections[] = ['heading' => $heading, 'paragraphs' => $paragraphs];
            }
            $content['kvkk']['sections'] = $sections;
        }
    }

    return $content;
}

$current = load_content();

match ($action) {
    'logout' => (function () {
        admin_logout();
        admin_redirect('/admin/login.php', 'ok', 'Oturum kapatıldı.');
    })(),
    'save_content' => (function () use ($current) {
        $posted = $_POST['content'] ?? null;
        if (!is_array($posted)) {
            admin_redirect('/admin/dashboard.php', 'error', 'Geçersiz içerik verisi.');
        }
        $merged = admin_normalize_content($posted, $current);
        if (!save_content($merged)) {
            admin_redirect('/admin/dashboard.php', 'error', 'İçerik kaydedilemedi.');
        }
        admin_redirect('/admin/dashboard.php', 'ok', 'İçerik kaydedildi.');
    })(),
    'upload_team_photo' => (function () use ($current) {
        $index = (int) ($_POST['member_index'] ?? -1);
        if ($index < 0 || !isset($current['team']['members'][$index])) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Geçersiz ekip üyesi.');
        }
        $file = $_FILES['photo'] ?? null;
        if (!is_array($file)) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Dosya seçilmedi.');
        }
        $result = save_uploaded_team_photo($file);
        if (!$result['ok']) {
            admin_redirect('/admin/dashboard.php#team', 'error', $result['error']);
        }
        delete_uploaded_file($current['team']['members'][$index]['photo'] ?? '');
        $current['team']['members'][$index]['photo'] = $result['path'];
        if (!save_content($current)) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Fotoğraf yolu kaydedilemedi.');
        }
        admin_redirect('/admin/dashboard.php#team', 'ok', 'Ekip fotoğrafı yüklendi.');
    })(),
    'remove_team_photo' => (function () use ($current) {
        $index = (int) ($_POST['member_index'] ?? -1);
        if ($index < 0 || !isset($current['team']['members'][$index])) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Geçersiz ekip üyesi.');
        }
        delete_uploaded_file($current['team']['members'][$index]['photo'] ?? '');
        $current['team']['members'][$index]['photo'] = '';
        if (!save_content($current)) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Fotoğraf kaldırılamadı.');
        }
        admin_redirect('/admin/dashboard.php#team', 'ok', 'Fotoğraf kaldırıldı.');
    })(),
    'delete_team_member' => (function () use ($current) {
        $rawIndex = $_POST['member_index'] ?? null;
        $index = filter_var($rawIndex, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
        if ($index === false || !isset($current['team']['members'][$index])) {
            admin_abort_with_status(422, 'Geçersiz ekip üyesi index değeri.');
        }

        $postedName = str_replace(["\r", "\n", "\0"], '', trim((string) ($_POST['member_name'] ?? '')));
        $serverName = trim((string) ($current['team']['members'][$index]['name'] ?? ''));
        if ($postedName === '' || $postedName !== $serverName) {
            admin_abort_with_status(409, 'Ekip üyesi sırası değişmiş olabilir. Önce kaydedin veya sayfayı yenileyin.');
        }

        $members = $current['team']['members'];
        $removed = $members[$index];
        unset($members[$index]);
        $current['team']['members'] = array_values($members);

        $removedPhoto = trim((string) ($removed['photo'] ?? ''));
        $canDeletePhoto = $removedPhoto !== '' && str_starts_with($removedPhoto, uploads_url_prefix() . '/');
        if ($canDeletePhoto) {
            foreach ($current['team']['members'] as $member) {
                if (($member['photo'] ?? '') === $removedPhoto) {
                    $canDeletePhoto = false;
                    break;
                }
            }
        }

        if (!save_content($current)) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Ekip üyesi silinemedi.');
        }

        if ($canDeletePhoto) {
            delete_uploaded_file($removedPhoto);
        }
        admin_redirect('/admin/dashboard.php#team', 'ok', 'Ekip üyesi silindi.');
    })(),
    'delete_process_step' => (function () use ($current) {
        $rawIndex = $_POST['step_index'] ?? null;
        $index = filter_var($rawIndex, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
        $steps = $current['process']['steps'] ?? [];
        if ($index === false || !isset($steps[$index])) {
            admin_abort_with_status(422, 'Geçersiz süreç adımı index değeri.');
        }

        $postedTitle = str_replace(["\r", "\n", "\0"], '', trim((string) ($_POST['step_title'] ?? '')));
        $serverTitle = trim((string) ($steps[$index]['title'] ?? ''));
        if ($postedTitle === '' || $postedTitle !== $serverTitle) {
            admin_abort_with_status(409, 'Süreç adımı sırası değişmiş olabilir. Önce kaydedin veya sayfayı yenileyin.');
        }

        unset($steps[$index]);
        $current['process']['steps'] = array_values($steps);

        if (!save_content($current)) {
            admin_redirect('/admin/dashboard.php#process', 'error', 'Süreç adımı silinemedi.');
        }
        admin_redirect('/admin/dashboard.php#process', 'ok', 'Süreç adımı silindi.');
    })(),
    'upload_asset' => (function () use ($current) {
        $assetKey = (string) ($_POST['asset_key'] ?? '');
        $allowed = ['logo_light', 'logo_dark', 'emblem', 'favicon', 'apple_touch_icon'];
        if (!in_array($assetKey, $allowed, true)) {
            admin_redirect('/admin/dashboard.php#media', 'error', 'Geçersiz varlık türü.');
        }
        $file = $_FILES['asset_file'] ?? null;
        if (!is_array($file)) {
            admin_redirect('/admin/dashboard.php#media', 'error', 'Dosya seçilmedi.');
        }
        $prefix = str_replace('_', '-', $assetKey);
        $result = save_uploaded_brand_image($file, $prefix);
        if (!$result['ok']) {
            admin_redirect('/admin/dashboard.php#media', 'error', $result['error']);
        }
        $jsonKey = $assetKey === 'logo_light' ? 'logo_light' : ($assetKey === 'logo_dark' ? 'logo_dark' : $assetKey);
        if ($assetKey === 'apple_touch_icon') {
            $jsonKey = 'apple_touch_icon';
        }
        $current['site']['assets'][$jsonKey] = $result['path'];
        if (!save_content($current)) {
            admin_redirect('/admin/dashboard.php#media', 'error', 'Varlık yolu kaydedilemedi.');
        }
        admin_redirect('/admin/dashboard.php#media', 'ok', 'Görsel yüklendi (yeni dosya yolu kaydedildi).');
    })(),
    'restore_backup' => (function () {
        $name = (string) ($_POST['backup_name'] ?? '');
        if (!restore_content_backup($name)) {
            admin_redirect('/admin/dashboard.php#backups', 'error', 'Yedek geri yüklenemedi.');
        }
        admin_redirect('/admin/dashboard.php', 'ok', 'Yedek geri yüklendi.');
    })(),
    default => admin_redirect('/admin/dashboard.php', 'error', 'Bilinmeyen işlem.'),
};
