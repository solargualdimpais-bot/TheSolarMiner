# Pen Owner e gestão de acessos

## Chave Owner offline

No primeiro registo, o Gateway gera uma chave de recuperação de utilização única e a PWA mostra-a uma vez. A PWA v0.5.9 permite descarregar essa chave e a fingerprint Ed25519 do Gateway como `solarminer-owner-recovery-key.txt`; copia o ficheiro para uma pen dedicada e remove cópias temporárias do computador. O ficheiro contém o segredo em texto simples. Quem o obtiver pode iniciar recuperação do Owner, por isso guarda a pen fisicamente em segurança.

A secção **Recuperar Owner com a pen** permite selecionar o ficheiro, criar uma identidade Ed25519 no browser e concluir o fluxo de recuperação com prova de desafio. A chave não é a chave privada Ed25519 de assinatura de releases, não contém credenciais GitHub, não valida certificados TLS e não desativa a autenticação. Depois de uma recuperação, a chave antiga é consumida; descarrega a nova chave e substitui o ficheiro na pen.

## Utilizadores reais

Na sessão Owner, a secção **Utilizadores e acessos reais** da PWA consulta `GET /api/v1/users` no Gateway e permite alterar papel ou estado através dos endpoints autenticados existentes. O Gateway exige a palavra-passe atual do Owner para cada alteração, regista a operação na auditoria e impede revogar ou despromover o último Owner ativo. A sessão atual não pode alterar o próprio papel ou estado. A promoção para Owner não é oferecida nesta interface; criação e recuperação de Owner ficam no fluxo dedicado que também gera a chave de recuperação.

Convites continuam a ser o método suportado para associar utilizadores e dispositivos novos. A edição manual do SQLite num computador não é suportada: uma cópia de uma base ativa pode omitir dados WAL e alterações SQL podem violar invariantes. Para administração normal, usa a PWA; para recuperação local, usa os comandos e backup descritos em `A2_OWNER_RECOVERY.md` e `DATABASE_BACKUP_AND_RESTORE.md`.

## Limites da pen

Inserir a pen não autentica automaticamente a PWA, não ignora a confiança TLS do iPhone e não concede root ao sistema operativo. O instalador e a chave pública de releases podem estar na mesma pen, mas a chave privada de assinatura nunca deve ser incluída. A recuperação Owner é uma credencial revogável; não é um bypass permanente e indetetável.
