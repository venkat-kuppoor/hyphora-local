The Hyphora CLI is the human computer interface for users to set up a [[Hyphora Vault]] and configure the [[Hyphora Context Retrieval Engine]]

# Technologies
- The will be built with Python and the Typer, a library for building CLI applications

# Options

`hyphora init`
- Will initialize a [[Hyphora Vault]] in the current directory

`hyphora init <project-name>`
- Will create a new directory with the user specified name and initialize a [[Hyphora Vault]] within it.

`hyphora update`
- Will update the hyphora cli; however, updates for a [[Hyphora Vault]] will be managed separately. Detailed in [[Hyphora Vault Updates]]

`hyphora sync`
- Will sync markdown Documents in a [[Hyphora Vault]] with sqlite db that is used by [[Hyphora Context Retrieval Engine]]
- 