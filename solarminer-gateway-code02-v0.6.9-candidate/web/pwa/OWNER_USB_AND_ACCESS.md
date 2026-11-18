# Pen Owner e gestão de acessos

## Chave Owner offline

No primeiro registo, o Gateway gera uma chave de recuperação de utilização única e a PWA mostra-a uma vez. A PWA permite guardar o ficheiro `solarminer-owner-recovery-key.txt` numa pen dedicada. O ficheiro contém o segredo em texto simples; guarda-o offline e protege fisicamente a pen.

A chave não é aceite por nenhum endpoint HTTP. A recuperação exige acesso local ao Gateway, terminal interativo com privilégios root e o serviço parado, conforme `docs/A2_OWNER_RECOVERY.md`. A PWA não consegue recuperar uma conta Owner.

## Utilizadores reais

Na sessão Owner, a secção **Utilizadores e acessos reais** da PWA consulta `GET /api/v1/users` no Gateway e permite alterar papel ou estado através dos endpoints autenticados existentes. O Gateway exige a palavra-passe atual do Owner para cada alteração, regista a operação na auditoria e impede revogar ou despromover o último Owner ativo. A sessão atual não pode alterar o próprio papel ou estado. A promoção para Owner não é oferecida nesta interface; o primeiro Owner é criado pelo fluxo de configuração e a recuperação é apenas local.

Convites continuam a ser o método suportado para associar utilizadores e dispositivos novos. A edição manual do SQLite num computador não é suportada: uma cópia de uma base ativa pode omitir dados WAL e alterações SQL podem violar invariantes. Para administração normal, usa a PWA; para recuperação local, usa os comandos e backup descritos em `A2_OWNER_RECOVERY.md` e `DATABASE_BACKUP_AND_RESTORE.md`.

## Limites da pen

Inserir a pen não autentica automaticamente a PWA, não ignora a confiança TLS do iPhone e não concede root ao sistema operativo. O instalador e a chave pública de releases podem estar na mesma pen, mas a chave privada de assinatura nunca deve ser incluída. A chave de recuperação Owner é uma credencial revogável; não é um bypass permanente e indetetável.
